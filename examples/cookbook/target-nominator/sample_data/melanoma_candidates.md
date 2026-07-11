# 黑色素瘤（melanoma）CAR-T / ADC 表面靶点候选清单（demo 微样例）

> 用于 target-nominator cookbook 的 GPNMB journey。候选取自黑色素瘤常见谱系抗原
> 与表面抗原。真实数据（表达 / 关联 / 可药性）由 cookbook 工具从 Human Protein Atlas +
> Open Targets **在线取数**，本文件只提供候选基因符号（不预填任何打分，避免"凭记忆"）。

## 候选基因

- GPNMB   # 跨膜糖蛋白，黑色素瘤高表达，抗体可药（glembatumumab vedotin ADC 背书）
- MLANA   # Melan-A / MART-1，黑色素瘤谱系抗原（多为胞内/黑素体，表面性弱）
- PMEL    # gp100 / PMEL17，黑色素瘤谱系抗原（黑素体）
- TYRP1   # 酪氨酸酶相关蛋白 1，黑色素瘤谱系抗原
- MCAM    # CD146，细胞黏附分子，真表面候选
- CSPG4   # NG2，硫酸软骨素蛋白聚糖，真表面候选

## 用法

```bash
python main.py --candidates-file sample_data/melanoma_candidates.md --cancer-type melanoma
```
