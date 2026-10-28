# UI 设计来源

后续生成的木框与纸张材质及其提示词见 [MATERIALS.md](MATERIALS.md)。

使用内置 imagegen 生成设计稿与背景，再对照实现 HTML/CSS 控件。医学图像始终来自服务器原文件；设计稿中的合成示意图不用于标注。

## 设计稿提示词

```text
Use case: ui-mockup
Asset type: High fidelity desktop web application UI design reference, landscape 1536x1024, flat front-on screenshot, no browser chrome.
Primary request: Design a polished Chinese-language corneal confocal microscopy annotation web app called "CCM 标注小屋", inspired by the cozy pixel farming game Stardew Valley. Warm cream parchment, restrained pixel wood edges, sage green selections, small pixel sprout icons, subtle low contrast farm hills and clouds outside the workspace. Must feel like a professional usable research annotation tool with refined spacing, not a game illustration.
Composition: header top with pixel sprout logo and "CCM 标注小屋", nav "标注工作台" active, "我的记录", "管理小屋", "操作手册", user "标注员". Below header a small kicker and title "今天，也认真看一张。" and right aligned green progress bar "128 / 1035". Main workspace two equal-ish columns. Left a parchment bordered image panel titled "图像观察窗", large square uncolored grayscale confocal image showing fine branching white nerve fibers on dark charcoal background inside a dark wood frame. Below are zoom minus plus 100%, "适应窗口", "1:1 原图", fullscreen icon. Muted small instruction "保持原始灰度与亮度，仅调整显示大小。".
Right panel titled "记录你的观察" all four questions visible. Q1 title "图像中可辨认出哪些层面？" exactly four checkbox-style rectangular option cards STACKED VERTICALLY in ONE COLUMN on left, each with its OWN horizontal three-stop slider on right labeled "少量 <10%", "中量 10–50%", "大量 >50%". Four cards: "基底下神经丛（SBNP）层", "角膜上皮细胞层", "角膜基质层", "其他 / 无法辨认 / 非角膜区域". Only first card green selected, slider at 大量; other cards beige unselected, sliders gray disabled.
Below Q2 "SBNP 整体可判读性" with four-stop horizontal slider "优 良 中 差", and Q3 "与 SBNP 的视觉混淆" with four-stop slider "不存在 分离良好 局部混淆 广泛混淆". For both select first option green.
Below Q4 "采集相关退化或伪影" with SIX checkbox cards in TWO COLUMNS THREE ROWS: "压力条纹 / 嵴 / 压痕", "运动模糊", "局部过亮 / 过曝", "局部过暗 / 曝光不足", "其他采集伪影", "不适用 · 未见明显伪影", last selected green.
Bottom of right panel status "草稿已保存" and dark sage green prominent button "保存并下一张 →". Small footer, subtle pixel leaf ornaments.
Style: clean precise grid, beautiful legible Chinese sans-serif body, elegant slightly literary Chinese heading, 2px tan borders with hard offset shadows, tiny pixel metal rivet corners on wood panel accents. No excessive ornament. Strong editorial hierarchy, generous but efficient spacing. Light warm theme, no purple, no gradients, no emojis, no invented navigation sections, no extra charts.
Constraints: UI mockup only; clinical image illustration here is a visual placeholder only. Keep all UI geometry practical for HTML/CSS implementation.
```

## 背景提示词

```text
Use case: illustration-story
Asset type: decorative background for a Chinese medical image annotation website, landscape 1536x1024.
Create a charming, restrained pixel-art countryside background inspired by Stardew Valley. Creamy warm pale sky across the top 35%, small light blue pixel clouds, distant layered sage blue and green hills along a horizon at 20% image height, little cedar trees, a small honey-colored cottage with terracotta roof at far upper right near the horizon, wooden fence and a gentle golden grassy field filling the lower scene. Fine old-school 16-bit game pixel art, tiny plants and sunflowers ONLY along left and right edges and lower corners. Main central 90% area below horizon is a quiet pale warm beige field with extremely sparse tiny grass pixels so cream UI panels overlay it clearly. Muted light sage greens, muted straw gold, warm pale ivory. No text, no letters, no labels, no panels, no buttons, no UI, no people, no animals, no medical imagery. Flat seamless-feeling horizontal landscape, daylight, cozy and calm, highly crafted pixel art.
```
