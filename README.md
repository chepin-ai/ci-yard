<!-- CLASSIFY: L0 -->
# ci-yard —— 公域承接仓（私仓 CI 的可替代面）

**定位**：承载全体系**公开安全**的 CI 计算面——lint、分类法检查、模拟器、基准、文档构建。私仓分钟耗尽期间，这里免费跑。
**边界（铁律）**：只载 L0/L1 内容；**机密、私仓结构、内部运作细节一律禁入**（CLASSIFY-01）；新 .md 必须带 `<!-- CLASSIFY: L0|L1 -->` 头，yard-smoke 会强制检查。
**分工**：公域试跑面=ci-yard（本仓）；私域借范特区=ci-build；治理/研究文书=ci-library；运行中枢=ci-control。
**接入**：guard-snap 机群快照已覆盖本仓；议题→ci-inbox 大厅 #144；指令轨=[CMD] 密封信封（root 专属）。
