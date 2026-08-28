"""Đường ống streaming — dựng đồ thị AML TĂNG DẦN theo từng giao dịch (Pha 1+).

Xem docs/ và kế hoạch: mỗi giao dịch tới = một cạnh mới; đồ thị lớn dần, không
có "cả cụm" như chế độ batch. Module này giữ trạng thái đồ thị sống trong các
bảng stream_* (db/init/032_stream_graph.sql).
"""
