"""
Minimal RIFE IFNet architecture for loading Practical-RIFE v4.x checkpoints.
Reference: https://github.com/hzwer/Practical-RIFE
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def conv(in_planes, out_planes, kernel_size=3, stride=1, padding=1, dilation=1):
    return nn.Sequential(
        nn.Conv2d(in_planes, out_planes, kernel_size=kernel_size, stride=stride,
                  padding=padding, dilation=dilation, bias=True),
        nn.PReLU(out_planes),
    )


class IFBlock(nn.Module):
    def __init__(self, in_planes, c=64):
        super().__init__()
        self.conv0 = nn.Sequential(
            conv(in_planes, c // 2, 3, 2, 1),
            conv(c // 2, c, 3, 2, 1),
        )
        self.convblock = nn.Sequential(
            conv(c, c), conv(c, c), conv(c, c), conv(c, c),
            conv(c, c), conv(c, c), conv(c, c), conv(c, c),
        )
        self.lastconv = nn.ConvTranspose2d(c, 5, 4, 2, 1)

    def forward(self, x, flow=None, scale=1):
        x = F.interpolate(x, scale_factor=1.0 / scale, mode="bilinear", align_corners=False)
        if flow is not None:
            flow = F.interpolate(flow, scale_factor=1.0 / scale, mode="bilinear", align_corners=False) / scale
            x = torch.cat([x, flow], 1)
        feat = self.conv0(x)
        feat = self.convblock(feat) + feat
        tmp = self.lastconv(feat)
        tmp = F.interpolate(tmp, scale_factor=scale * 2, mode="bilinear", align_corners=False)
        flow = tmp[:, :4] * scale * 2
        mask = tmp[:, 4:5]
        return flow, mask


class IFNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.block0 = IFBlock(7, c=192)
        self.block1 = IFBlock(8 + 4, c=128)
        self.block2 = IFBlock(8 + 4, c=96)
        self.block3 = IFBlock(8 + 4, c=64)

    def forward(self, img0, img1, timestep=0.5):
        imgs = torch.cat([img0, img1], 1)
        t = torch.full_like(img0[:, :1, :, :], timestep)
        f0, m0 = self.block0(torch.cat([imgs, t], 1), None, scale=8)
        f1, m1 = self.block1(torch.cat([imgs, t, f0], 1), f0, scale=4)
        f2, m2 = self.block2(torch.cat([imgs, t, f1], 1), f1, scale=2)
        f3, m3 = self.block3(torch.cat([imgs, t, f2], 1), f2, scale=1)
        flow = f3
        mask = torch.sigmoid(m3)
        grid_y, grid_x = torch.meshgrid(
            torch.arange(img0.shape[2], device=img0.device, dtype=img0.dtype),
            torch.arange(img0.shape[3], device=img0.device, dtype=img0.dtype),
            indexing='ij',
        )
        grid = torch.stack([grid_x, grid_y], dim=0).unsqueeze(0)
        def warp(img, flow_xy):
            warped_grid = grid + flow_xy
            warped_grid[:, 0] = 2.0 * warped_grid[:, 0] / (img.shape[3] - 1) - 1.0
            warped_grid[:, 1] = 2.0 * warped_grid[:, 1] / (img.shape[2] - 1) - 1.0
            warped_grid = warped_grid.permute(0, 2, 3, 1)
            return F.grid_sample(img, warped_grid, mode='bilinear', padding_mode='border', align_corners=True)
        warped0 = warp(img0, flow[:, :2])
        warped1 = warp(img1, flow[:, 2:4])
        return warped0 * mask + warped1 * (1 - mask)
