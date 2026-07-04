"""FeedbackTransport 介面（v1 唯一實作 GoogleFormTransport；此介面即二期預留）。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.services.feedback.diagnostics import DiagnosticsSections


@dataclass
class FeedbackReport:
    type_label: str                          # 已對映成中文的表單選項字串
    description: str
    email: str | None
    include_diagnostics: bool
    sections: DiagnosticsSections | None     # include_diagnostics=False 時為 None
    app_version: str                         # 欄位 4 永遠送，永遠有值


class FeedbackTransport(ABC):
    @abstractmethod
    def submit(self, report: FeedbackReport) -> None:
        """送出回報；失敗 raise FeedbackTransportError。"""
