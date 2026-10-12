"""PACE policy: per-node scoring network (size-agnostic) + DEFER head + critic.

Each candidate node is scored by the same MLP over [node features, task/global
features], so the policy handles any number of nodes and masks dead/forbidden ones.
The preference weight w is part of the task/global features (preference conditioning).
"""
from __future__ import annotations

import torch
import torch.nn as nn

from .features import F_N, F_T, K_MAX

NEG = -1e9


class PACENet(nn.Module):
    def __init__(self, hidden: int = 128):
        super().__init__()
        self.node = nn.Sequential(nn.Linear(F_N + F_T, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU())
        self.score = nn.Linear(hidden, 1)
        self.defer = nn.Sequential(nn.Linear(F_T, 64), nn.ReLU(), nn.Linear(64, 1))
        self.value = nn.Sequential(nn.Linear(F_T + 2 * hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1))

    def forward(self, xn: torch.Tensor, xt: torch.Tensor, mask: torch.Tensor):
        B = xn.shape[0]
        h = self.node(torch.cat([xn, xt.unsqueeze(1).expand(B, K_MAX, F_T)], dim=-1))
        logits = torch.cat([self.score(h).squeeze(-1), self.defer(xt)], dim=-1)
        logits = logits.masked_fill(~mask, NEG)
        nm = mask[:, :K_MAX].unsqueeze(-1)
        hmax = h.masked_fill(~nm, NEG).max(dim=1).values
        hmean = (h * nm).sum(1) / nm.sum(1).clamp(min=1)
        v = self.value(torch.cat([xt, hmax, hmean], dim=-1)).squeeze(-1)
        return logits, v
