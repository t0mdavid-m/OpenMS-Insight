import pandas as pd
import plotly.express as px
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

def run_and_plot_pca(expr_df_pca: pd.DataFrame, group_map: dict):
    """
    OpenMS-Insight 내장용 PCA 계산 및 Plotly 객체 반환 함수
    """
    # 1. 데이터 전처리 및 PCA 실행
    X = expr_df_pca.T
    X_scaled = StandardScaler().fit_transform(X)
    
    pca = PCA(n_components=2)
    pcs = pca.fit_transform(X_scaled)
    
    pca_df = pd.DataFrame(
        pcs,
        columns=["PC1", "PC2"],
        index=X.index
    )
    
    # 2. 그룹 매핑 (.mzML 확장자 제거 처리 포함)
    norm_map = {k.replace(".mzML", ""): v for k, v in group_map.items()}
    pca_df["Group"] = pca_df.index.map(norm_map)
    
    # 3. Plotly 시각화 객체 생성
    fig_pca = px.scatter(
        pca_df,
        x="PC1",
        y="PC2",
        color="Group",
        text=pca_df.index,
    )
    
    fig_pca.update_traces(textposition="top center")
    fig_pca.update_layout(
        xaxis_title=f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)",
        yaxis_title=f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)",
        height=600,
    )
    
    return fig_pca, expr_df_pca.shape[0]