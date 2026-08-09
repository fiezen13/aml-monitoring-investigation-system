# Báo cáo Toán học & Data Science — Pipeline Risk Scoring AML

**Đối tượng:** Isolation Forest + Graph Topology + Rule Fusion  
**Nguồn sự thật trong code:**  
`scripts/ingest_data.py` → `extract_features.py` → `train_isolation_forest.py` → `evaluate_model.py`

---

## 0. Pipeline dưới góc nhìn ánh xạ

\[
\text{Event sequence } \mathcal{E}
\;\xrightarrow{\;\Phi\;}
\mathbf{X}_a \in \mathbb{R}^{d}
\;\xrightarrow{\;f_{\text{IF}},\,f_{G},\,f_{R}\;}
(\text{ml},\,\text{graph},\,\text{rule})
\;\xrightarrow{\;w^{\top}\;}
\text{Risk}(a)
\;\xrightarrow{\;\tau^{\*}\;}
\hat{y}(a)
\]

| Bước | Hàm trong code | Ý nghĩa |
|---|---|---|
| Ingest + ND1/ND2 | `ingest_data()`, `_read_ibm_csv()` | Tách nhãn; time-split 60/20/20 |
| Feature map \(\Phi\) | `_to_account_events()`, `extract_split_features()` | Event → vector account |
| IF + Graph + Rules | `train_and_score()`, `_score_split()` | Ba nhánh điểm |
| Ngưỡng tối ưu | `_find_best_threshold()` | \(\tau^\*\) trên Val, áp Test |

**Lưu ý quan trọng:** file feature có **12 cột** (`cols=12`), trong đó 1 cột định danh `account_key` và **\(d = 11\)** đặc trưng số. Isolation Forest chỉ fit trên 11 cột số (`_feature_cols()` bỏ `account_key`).

---

## 1. Biến đổi không gian đặc trưng

### 1.1. Không gian thô → không gian account

Mỗi giao dịch thô (sau ingest):

\[
e = \big(t,\; u_{\text{from}},\; u_{\text{to}},\; b_{\text{from}},\; b_{\text{to}},\; m\big)
\]

với \(m =\) `Amount Paid`, khóa  
\(u = \texttt{str(Bank)}+\texttt{":"}+\texttt{str(Account)}\)  
(`ingest_data.py` / `_read_ibm_csv`).

**Bước bung 2 chiều** — `_to_account_events()`: mỗi \(e\) tạo 2 sự kiện account-level:

- **Credit (IN)** tại \(u_{\text{to}}\): \((t, a=u_{\text{to}}, m_{\text{in}}=m, m_{\text{out}}=0)\)
- **Debit (OUT)** tại \(u_{\text{from}}\): \((t, a=u_{\text{from}}, m_{\text{in}}=0, m_{\text{out}}=m)\)

Gọi tập sự kiện của account \(a\) trong một split là \(\mathcal{E}_a\), và

\[
T^{\*} = \max_{e \in \mathcal{E}_{\text{split}}} t(e)
\]

(neo cửa sổ theo **max timestamp của cả split**, không phải theo từng account — `extract_split_features()`).

Mask cửa sổ:

\[
\mathbf{1}_{W}(e) = \mathbf{1}\big\{t(e) \ge T^{\*} - W\big\}, \quad W \in \{1\text{d},\,7\text{d},\,30\text{d}\}
\]

### 1.2. Danh sách 11 đặc trưng \(X_a \in \mathbb{R}^{11}\)

Với mọi \(e \in \mathcal{E}_a\), định nghĩa indicator cấp sự kiện:

\[
\begin{aligned}
I_{\text{near}}(e) &= \mathbf{1}\{9000 \le m(e) < 10000\} \\
I_{\text{off}}(e) &= \mathbf{1}\{\text{hour}(t(e)) \in \{0,1,2,3,4,5\}\} \\
I_{\text{ib}}(e) &= \mathbf{1}\{b_{\text{from}}(e) \neq b_{\text{to}}(e)\}
\end{aligned}
\]

| # | Tên cột | Định nghĩa toán học | Code |
|---:|---|---|---|
| 1 | `vol_1d` | \(\displaystyle\sum_{e\in\mathcal{E}_a} m(e)\,\mathbf{1}_{1d}(e)\) | `amt_1d.sum()` |
| 2 | `vol_7d` | \(\displaystyle\sum_{e\in\mathcal{E}_a} m(e)\,\mathbf{1}_{7d}(e)\) | `amt_7d.sum()` |
| 3 | `vol_30d` | \(\displaystyle\sum_{e\in\mathcal{E}_a} m(e)\,\mathbf{1}_{30d}(e)\) | `amt_30d.sum()` |
| 4 | `tx_cnt_1d` | \(\displaystyle\sum_{e\in\mathcal{E}_a} \mathbf{1}_{1d}(e)\) | `cnt_1d.sum()` |
| 5 | `tx_cnt_7d` | \(\displaystyle\sum_{e\in\mathcal{E}_a} \mathbf{1}_{7d}(e)\) | `cnt_7d.sum()` |
| 6 | `tx_cnt_30d` | \(\displaystyle\sum_{e\in\mathcal{E}_a} \mathbf{1}_{30d}(e)\) | `cnt_30d.sum()` |
| 7 | `near_threshold_ratio` | \(\displaystyle\frac{1}{|\mathcal{E}_a|}\sum_{e\in\mathcal{E}_a} I_{\text{near}}(e)\) | `is_near_threshold.mean()` |
| 8 | `credit_debit_ratio` | \(\displaystyle\frac{\sum m_{\text{in}}}{\sum m_{\text{out}} + 10^{-6}}\) | `extract_split_features` |
| 9 | `amount_std` | \(\sigma\big(\{m(e): e\in\mathcal{E}_a\}\big)\) (theo Polars `std`) | `amount.std()` |
| 10 | `off_hour_ratio` | \(\displaystyle\frac{1}{|\mathcal{E}_a|}\sum I_{\text{off}}(e)\) | `is_off_hour.mean()` |
| 11 | `interbank_ratio` | \(\displaystyle\frac{1}{|\mathcal{E}_a|}\sum I_{\text{ib}}(e)\) | `is_interbank.mean()` |

Viết gọn vector:

\[
X_a =
\big[
\text{vol}_{1d},\;
\text{vol}_{7d},\;
\text{vol}_{30d},\;
\text{cnt}_{1d},\;
\text{cnt}_{7d},\;
\text{cnt}_{30d},\;
r_{\text{near}},\;
\rho_{C/D},\;
\sigma_m,\;
r_{\text{off}},\;
r_{\text{ib}}
\big]^{\top}
\in \mathbb{R}^{11}
\]

**ND1:** `Is Laundering` **không** nằm trong \(X\) — tách ở `labels.csv` (`ingest_data()`).  
**ND2:** \(\Phi\) chạy **riêng từng split** train/val/test (`extract_features()`).

---

## 2. Bản chất toán học của các nhánh mô hình

### 2.1. Isolation Forest — nguyên lý phân tách

**File/hàm:** `train_isolation_forest.py` → `train_and_score()`  

Hyperparameters:

\[
n_{\text{estimators}}=100,\;
\text{contamination}=5\cdot 10^{-4},\;
\text{random\_state}=42,\;
n_{\text{jobs}}=-1
\]

**Ý tưởng (Liu et al., 2008):** điểm bất thường “dễ cô lập” hơn điểm bình thường → độ sâu đường đi trên cây ngẫu nhiên ngắn hơn.

Với rừng \(\{T_k\}_{k=1}^{K}\), \(K=100\):

\[
E\big(h(x)\big) = \frac{1}{K}\sum_{k=1}^{K} h_k(x)
\]

\(h_k(x)\): độ sâu (path length) của \(x\) trên cây \(k\).

Chuẩn hóa theo kích thước mẫu \(n\) (hàm \(c(n)\) của binary search tree trung bình):

\[
c(n) = 2H(n-1) - \frac{2(n-1)}{n}, \quad H(i) \approx \ln i + \gamma
\]

**Anomaly score cổ điển:**

\[
s(x,n) = 2^{-\,E(h(x))/c(n)} \in (0,1]
\]

- \(s \to 1\): bất thường (path ngắn)
- \(s \to 0\): bình thường (path dài)

**Trong sklearn:** `decision_function(x)` tỉ lệ nghịch với mức bất thường (càng **âm** càng bất thường). Code dùng trực tiếp giá trị này rồi đảo Min-Max — xem mục 3.2 (`_raw_to_ml_score`).

Fit **chỉ trên train:**

\[
\hat{f}_{\text{IF}} = \text{IsolationForest fit on } \{X_a\}_{a\in\text{Train}}
\]

(`model.fit(X_train)`).

---

### 2.2. Graph engine (NetworkX) — topology

**Hàm:** `_graph_scores_from_tx(tx_path)`

1. **Aggr cạnh có trọng số** (Polars, không duyệt từng TX):

\[
w(u,v) = \sum_{\substack{e:\\u_{\text{from}}=u,\,u_{\text{to}}=v}} m(e)
\]

2. Đồ thị có hướng \(G=(V,E)\), `nx.DiGraph`.

3. **Degree:**

\[
\deg^{-}(a)=\text{in-degree},\quad
\deg^{+}(a)=\text{out-degree}
\]

\[
\text{deg\_score}(a)=\min\big(15\cdot(\deg^{-}+\deg^{+}),\; 70\big)
\]

4. **Chu trình (proxy quy mô lớn):**  
   Không chạy `nx.simple_cycles` (không khả thi ~10⁶ cạnh). Dùng:

\[
\mathcal{C} =
\big\{ v : v\in S,\; |S|>1,\; S\in \mathrm{SCC}(G) \big\}
\;\cup\;
\big\{ v : (v,v)\in E \big\}
\]

(`nx.strongly_connected_components` + self-loop).

\[
\text{cycle\_score}(a)=30\cdot\mathbf{1}\{a\in\mathcal{C}\}
\]

\[
\text{GraphScore}(a)=\min\big(\text{deg\_score}+\text{cycle\_score},\;100\big)
\]

---

### 2.3. Rule engine — tổng các hàm bước

**Hàm:** `_rule_scores()`

\[
\begin{aligned}
R(a)
&= 40\cdot\mathbf{1}\{\text{vol}_{30d}(a) > 30000\} \\
&\quad + 30\cdot\mathbf{1}\{r_{\text{near}}(a) > 0\} \\
&\quad + 30\cdot\mathbf{1}\{r_{\text{off}}(a) > 0.3\}
\end{aligned}
\]

\[
\text{RuleScore}(a)=\min\big(R(a),\,100\big)
\]

Đây là tổ hợp tuyến tính của **indicator / step functions** trên không gian đặc trưng.

---

## 3. Score Fusion & Optimal Thresholding

### 3.1. Công thức Risk Score

**Hàm:** `_score_split()`

\[
\boxed{
\mathrm{Risk}(a)
=
0.5\,\mathrm{ML}(a)
+
0.3\,\mathrm{Graph}(a)
+
0.2\,\mathrm{Rule}(a)
}
\]

tức \(w=(0.5,\,0.3,\,0.2)\), \(\|w\|_1=1\).

---

### 3.2. Chuẩn hóa `decision_function` → `[0,100]`

**Hàm:** `_raw_to_ml_score(raw, min_s, max_s)`

Gọi \(r(a)=\texttt{decision\_function}(X_a)\).  
Neo scale **chỉ từ train:**

\[
r_{\min}=\min_{a\in\text{Train}} r(a),\quad
r_{\max}=\max_{a\in\text{Train}} r(a)
\]

**Đảo Min-Max** (vì \(r\) càng nhỏ → càng bất thường):

\[
\boxed{
\mathrm{ML}(a)
=
\mathrm{clip}_{[0,100]}
\left(
100\cdot\frac{r_{\max}-r(a)}{r_{\max}-r_{\min}}
\right)
}
\]

Nếu \(r_{\max}=r_{\min}\): gán \(\mathrm{ML}=50\).

---

### 3.3. Ngưỡng tối ưu trên Validation

**Hàm:** `_find_best_threshold()` · hằng `TARGET_RECALL = 0.80`

Dự đoán:

\[
\hat{y}_\tau(a)=\mathbf{1}\{\mathrm{Risk}(a)\ge \tau\}
\]

**Bài toán tối ưu (đúng với code — không phải \(\arg\max F_1\)):**

\[
\boxed{
\tau^{\*}
=
\arg\min_{\tau}
\;
\big|\{\,a:\mathrm{Risk}(a)\ge\tau\,\}\big|
\quad
\text{s.t.}
\quad
\mathrm{Recall}(\tau)\ge 0.80
}
\]

Tức: **minimize alert volume** subject to **Recall ≥ 80%**.  
Nếu không khả thi: fallback \(\arg\max\) Recall, tie-break ít alert.

\(\tau^{\*}\) học trên Val, áp nguyên lên Test (`evaluate_model()`).  
Kết quả thực nghiệm gần nhất: \(\tau^{\*}=12.22\).

---

## 4. Đầu ra & ý nghĩa kỹ thuật / nghiệp vụ

### 4.1. Biến số output hiện tại

Từ `scored_{train,val,test}.csv` (`_score_split`):

| Biến | Miền | Ý nghĩa |
|---|---|---|
| `ml_score` | \([0,100]\) | Mức bất thường hành vi (IF) |
| `graph_score` | \([0,100]\) | Rủi ro cấu trúc mạng |
| `rule_score` | \([0,100]\) | Vi phạm luật cứng AML |
| `risk_score` | \([0,100]\) (xấp xỉ) | Điểm xếp hạng tổng hợp |
| (+ 11 features gốc) | \(\mathbb{R}^{11}\) | Giải thích / audit |

**Không còn** xuất `is_anomaly` / `typology_code` trong bản train hiện tại — quyết định alert nằm ở bước evaluate qua \(\tau^{\*}\):

\[
\hat{y}(a)=\mathbf{1}\{\mathrm{Risk}(a)\ge\tau^{\*}\}
\]

Artifact: `data/isolation_forest_model.joblib`, `data/processed/best_threshold.txt`.

---

### 4.2. Từ Unsupervised → Risk Ranking

1. **IF không cần nhãn khi fit** → học cấu trúc “độ cô lập” trên \(\mathbb{R}^{11}\).
2. **Graph + Rules** thêm inductive bias AML (mạng, structuring, off-hour).
3. **Fusion tuyến tính** tạo một scalar ranking \(\mathrm{Risk}(a)\).
4. **Nhãn chỉ dùng ở Val/Test** để chọn \(\tau\) và đo Precision/Recall/AUC — không backprop vào IF.

**Giá trị cho analyst:** thay vì duyệt đồng đều \(N\) account, sắp xếp theo \(\mathrm{Risk}\) giảm dần và cắt tại \(\tau\). Về lý thuyết, nếu ranking tốt thì cùng một ngân sách alert \(K\) sẽ maximize số case thật bắt được (liên hệ PR-curve / Recall@K).

**Thực tế LI-Small (để nói thẳng với nhóm):**  
để ép Recall ≥ 80% buộc \(\tau\) thấp → alert rất lớn (Val ~78% FPR). ROC-AUC Test ~0.69 cho thấy **có tín hiệu xếp hạng**, nhưng **chưa đủ tách lớp dương siêu hiếm** (~0.3%) để vừa Recall cao vừa alert ít. Đó là hạn chế của feature space + unsupervised IF + graph proxy SCC, không phải lỗi công thức fusion.

#### Bảng kết quả evaluate gần nhất

**VALIDATION** @ `best_thresh = 12.22` (target Recall ≥ 80%)

| Metric | Value |
|---|---:|
| N accounts | 322,132 |
| N positive | 1,340 |
| N alerts | 251,658 |
| ROC-AUC | 0.5776 |
| PR-AUC | 0.0078 |
| Precision | 0.0043 |
| Recall | 0.8022 |
| F1-Score | 0.0085 |
| FPR | 0.7811 |

**TEST** @ cùng threshold

| Metric | Value |
|---|---:|
| N accounts | 486,489 |
| N positive | 1,414 |
| N alerts | 301,465 |
| ROC-AUC | 0.6894 |
| PR-AUC | 0.0098 |
| Precision | 0.0039 |
| Recall | 0.8225 |
| F1-Score | 0.0077 |
| FPR | 0.6191 |

---

## 5. Sơ đồ tóm tắt cho slide nhóm

```text
TX events  --Φ(groupby, windows)-->  X ∈ R^11
                                      |
          +---------------------------+---------------------------+
          |                           |                           |
     IsolationForest            Digraph G=(V,E)              Step rules
     decision_function          deg + SCC/self-loop          40/30/30
          |                           |                           |
     MinMax^{-1}→[0,100]         GraphScore∈[0,100]         RuleScore∈[0,100]
          |                           |                           |
          +--------- Risk = 0.5 ML + 0.3 Graph + 0.2 Rule --------+
                                      |
                         τ* = argmin #alerts s.t. Recall≥0.8 (Val)
                                      |
                              Alert ranking on Test
```

---

## 6. Chỉ mục đối soát code (cheat-sheet)

| Khái niệm | File | Hàm |
|---|---|---|
| Account key `Bank:Account` | `ingest_data.py` | `_read_ibm_csv` |
| ND1 labels / ND2 split | `ingest_data.py` | `ingest_data` |
| Event→2 chiều IN/OUT | `extract_features.py` | `_to_account_events` |
| Aggregation \(\Phi\) | `extract_features.py` | `extract_split_features` |
| Fit IF train-only | `train_isolation_forest.py` | `train_and_score` |
| Min-Max đảo | `train_isolation_forest.py` | `_raw_to_ml_score` |
| Graph degree + SCC | `train_isolation_forest.py` | `_graph_scores_from_tx` |
| Rule indicators | `train_isolation_forest.py` | `_rule_scores` |
| Fusion \(0.5/0.3/0.2\) | `train_isolation_forest.py` | `_score_split` |
| \(\tau^\*\) min-alerts s.t. Rec≥0.8 | `evaluate_model.py` | `_find_best_threshold` |

---

## 7. Cách chạy lại pipeline

```bash
make ml-pipeline
# tương đương:
# python scripts/ingest_data.py && \
# python scripts/extract_features.py && \
# python scripts/train_isolation_forest.py && \
# python scripts/evaluate_model.py
```

Artifact chính:

- `data/processed/features_{train,val,test}.csv`
- `data/processed/scored_{train,val,test}.csv`
- `data/isolation_forest_model.joblib`
- `data/processed/best_threshold.txt`
- `data/processed/evaluation_report.txt`
