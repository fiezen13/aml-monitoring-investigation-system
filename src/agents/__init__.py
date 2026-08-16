"""KHUNG MẪU ĐÃ NGỪNG DÙNG — không nối gói này vào bất cứ đâu.

Đây là bộ khung LangGraph sinh sẵn (``example_node``, ``example_tool``) với các
hàm chỉ trả về chuỗi ghép từ đầu vào:

    analysis = f"Phân tích: {query}"

Nó KHÔNG phải tầng tác tử của hệ thống. Ba tác tử thật —
``investigation_supervisor``, ``explanation_agent``, ``evidence_critic`` — nằm ở
``src/investigation/`` cùng với ngân sách an toàn, sổ bằng chứng và bộ phản biện
tất định.

Trước đây gói này được nối vào ``POST /api/v1/chat``, tức là một endpoint công
khai của bảng điều khiển AML trả về văn bản "phân tích" bịa ra. Endpoint đã bị
gỡ. Phần còn lại ở đây là mã chết, giữ nguyên chỉ để việc xoá được rà soát riêng
trong một thay đổi độc lập.

Xoá bằng::

    git rm -r src/agents tests/test_agents
    # rồi bỏ langchain / langgraph khỏi requirements.txt nếu không còn ai dùng
"""
