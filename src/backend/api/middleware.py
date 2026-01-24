import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID, uuid4

from fastapi import Request, Response
from starlette import status
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


LOGGER = logging.getLogger(__name__)


class RequestHandlingMiddleware(BaseHTTPMiddleware):
    def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        request_time: float = datetime.now(tz=ZoneInfo('UTC')),
        # app_session_id: UUID = '00000000-0000-0000-0000-000000000000',
    ) -> Response:
        """
        根結點中間層，用於計算路由節點總計算時間；若處理發生錯誤，則擷取錯誤訊息傳遞給使用者。

        Args:
        - **request** (Request): 客戶端請求
        - **call_next** (RequestResponseEndpoint): 執行下一層路由
        - **request_time** (float, optional): 取得接收請求當下時間. Defaults is datetime in utc0.
        - **app_session_id** (UUID, optional): 為請求建立UUID，用於錯誤追蹤. Defaults to uuid4().

        Returns:
        - **Response**: 回傳給客戶端的響應資料
        """

        request.state.app_session_id = uuid4()

        LOGGER.info(f"Request initializng, AppSessionID={request.state.app_session_id}")

        response: Response = None

        try:
            response = call_next(request)
            
        except ValueError as e:
            LOGGER.info(
                f"Request processing error, AppSessionID={request.state.app_session_id}, Error={str(e)}")
            response = JSONResponse(
                headers={},
                status_code=status.HTTP_200_OK,
                content=f"處理編號:{request.state.app_session_id}, 訊息:{str(e)}",
            )
        except Exception as e:
            LOGGER.warning(
                f"Request processing error, AppSessionID={request.state.app_session_id}, Error={str(e)}")
            response = JSONResponse(
                headers={},
                status_code=status.HTTP_409_CONFLICT,
                content=f"處理失敗。處理編號:{request.state.app_session_id}, 錯誤訊息:{str(e)}",
            )

        process_time: timedelta = f"{(datetime.now(tz=ZoneInfo('UTC')) - request_time).total_seconds()}"
        response.headers["X-Process-Time"] = process_time

        LOGGER.info(
            f"Request processing done, AppSessionID={request.state.app_session_id}, X-Process-Time={process_time}s"
        )

        return response
