"""Detection Engine — các nhánh phát hiện của FIN-07.

Ba nhánh trong kiến trúc:

* **rule** — ``src/detection/rules.py`` + ``src/detection/rule_engine.py``.
  Luật tất định, giải thích được bằng dữ liệu thô.
* **anomaly** — Isolation Forest, xem ``src/behavior/`` và
  ``scripts/train_isolation_forest.py``.
* **graph** — detector FAN / GATHER_SCATTER / CYCLE, xem
  ``scripts/run_graph_pipeline.py`` và bộ nạp ``src/detection/graph_loader.py``.

Việc hợp nhất ba nhánh thuộc ``src/fusion``. Không nhánh nào được tự quyết điểm
cuối cùng.
"""
