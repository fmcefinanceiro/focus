import os
import io
import zipfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# =========================================================
# 1) CONFIGURAÇÕES GERAIS DO PROJETO
#    -> EDITE AQUI quando quiser adaptar para outra empresa
# =========================================================
CONFIG = {
    "app": {
        "page_title": "FP&A Dashboard",
        "page_icon": "📊",
        "layout": "wide",
        "titulo_principal": "Dashboard FP&A",
        "logo_sidebar": "Assinatura visual 11B.png",
        "menu": [
            "Dashboard",
            "Dashboard Focus IC",
            "Dashboard Focus AD",
            "Demonstrativo",
            "Demonstrativo Focus IC",
            "Demonstrativo Focus AD",
            "Downloads"
        ]
    },

    "arquivo": {
        "sheet_name": 0
    },

    "colunas": {
        "data": "Dt. Pagamento",
        "grupo": "Grupo",
        "conta": "Conta Financeira",
        "valor": "Valor Pago",
        "unidade": "Unidade"
    },

    "mapa_grupos": {
        "3.1.1.01 RECEITAS DE PRESTAÇÃO DE SERVIÇO": "Receita Bruta",
        "3.1.1.02 RECEITA DE CURSOS": "Receita Bruta",
        "3.2.1.01. IMPOSTOS SOBRE RECEITA": "Deduções",
        "4.1.1.01 CUSTOS MATERIAIS DIRETOS": "Custos Variáveis",
        "4.1.1.02 CUSTOS COM PESSOAL - TÉCNICOS": "Custos Variáveis",
        "4.1.1.03 CUSTOS COM ATENDIMENTO EXTERNO": "Custos Variáveis",
        "4.2.1.01 DESPESAS COM PESSOAL": "Custos Fixos",
        "4.2.1.02 DESPESAS ADMINISTRATIVAS": "Custos Fixos",
        "4.2.2.01 DESPESAS TRIBUTÁRIAS": "Custos Fixos",
        "4.2.3.01 DESPESAS FINANCEIRAS": "Custos Fixos",
        "6.1.1.01 DESPESAS NÃO DEDUTÍVEIS": "Antecipações e Retiradas de Lucros",
        "7.1.1.01 INVESTIMENTOS EM ESTRUTURA CLÍNICA": "Investimentos"
    },

    "grupos_negativos": [
        "Deduções",
        "Custos Variáveis",
        "Custos Fixos",
        "Antecipações e Retiradas de Lucros",
        "Investimentos"
    ],

    "estrutura_dre": [
        {"nome": "Receita Bruta", "tipo": "grupo", "origem": "Receita Bruta"},
        {"nome": "(-) Deduções", "tipo": "grupo", "origem": "Deduções"},
        {"nome": "(-) Custos Variáveis", "tipo": "grupo", "origem": "Custos Variáveis"},
        {"nome": "Margem de Contribuição", "tipo": "formula", "formula": ["Receita Bruta", "(-) Deduções", "(-) Custos Variáveis"]},
        {"nome": "Custos / Despesas", "tipo": "grupo", "origem": "Custos Fixos"},
        {"nome": "Resultado Operacional", "tipo": "formula", "formula": ["Margem de Contribuição", "Custos / Despesas"]},
        {"nome": "Antecipações e Retiradas de Lucros", "tipo": "grupo", "origem": "Antecipações e Retiradas de Lucros"},
        {"nome": "Resultado Líquido", "tipo": "formula", "formula": ["Resultado Operacional", "Antecipações e Retiradas de Lucros"]},
        {"nome": "Investimentos", "tipo": "grupo", "origem": "Investimentos"},
        {"nome": "Saldo Operacional", "tipo": "formula", "formula": ["Resultado Líquido", "Investimentos"]},
    ],

    "linha_receita_base_av": "Receita Bruta",

    "downloads": {
        "arquivo_zip": "data/Focus - Arquivos entregues.zip"
    },
}


# =========================================================
# 2) CONFIG STREAMLIT
# =========================================================
st.set_page_config(
    page_title=CONFIG["app"]["page_title"],
    page_icon=CONFIG["app"]["page_icon"],
    layout=CONFIG["app"]["layout"]
)

st.title(CONFIG["app"]["titulo_principal"])

logo_path = CONFIG["app"]["logo_sidebar"]
if logo_path and os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)

st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] { background-color: #002d70; }
        section[data-testid="stSidebar"] * { color: white; }
        section[data-testid="stSidebar"] label { color: white; font-weight: 600; }
        section[data-testid="stSidebar"] div[role="radiogroup"] label { color: white; }
        section[data-testid="stSidebar"] .stRadio > div { background: transparent; }
    </style>
    """,
    unsafe_allow_html=True
)

menu = st.sidebar.radio("Navegação", CONFIG["app"]["menu"])

st.sidebar.markdown("---")
st.sidebar.markdown("### 📂 Carregar base")

arquivo_upload = st.sidebar.file_uploader(
    "Envie a base financeira (.xlsx)",
    type=["xlsx"]
)


# =========================================================
# 3) FUNÇÕES AUXILIARES
# =========================================================
def formato_contabil(valor):
    if pd.isna(valor):
        return ""
    valor_abs = abs(valor)
    texto = (
        f"R$ {valor_abs:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
    return f"({texto})" if valor < 0 else texto


def formato_percentual(valor):
    if pd.isna(valor):
        return ""
    valor_abs = abs(valor)
    texto = f"{valor_abs:.1f}%"
    return f"({texto})" if valor < 0 else texto


def estilo_financeiro(valor):
    if not isinstance(valor, (int, float)):
        return ""
    if pd.isna(valor):
        return ""
    return "color: red;" if valor < 0 else ""


def mm_cumulativa(serie):
    return serie.expanding(min_periods=1).mean()


def gerar_rotulo_mes(data_series):
    meses_pt = {
        1: "jan", 2: "fev", 3: "mar", 4: "abr",
        5: "mai", 6: "jun", 7: "jul", 8: "ago",
        9: "set", 10: "out", 11: "nov", 12: "dez"
    }
    return data_series.dt.month.map(meses_pt) + "/" + data_series.dt.year.astype(str)


def listar_arquivos_para_download(pasta_base):
    pasta = Path(pasta_base)

    if not pasta.exists() or not pasta.is_dir():
        return []

    arquivos = [p for p in pasta.rglob("*") if p.is_file()]
    arquivos = sorted(arquivos, key=lambda x: str(x).lower())
    return arquivos


def obter_mime_type(caminho_arquivo):
    ext = caminho_arquivo.suffix.lower()

    mapa = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt": "text/plain",
        ".zip": "application/zip"
    }

    return mapa.get(ext, "application/octet-stream")


def criar_zip_da_pasta(pasta_base):
    buffer = io.BytesIO()
    pasta = Path(pasta_base)

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for arquivo in pasta.rglob("*"):
            if arquivo.is_file():
                arcname = arquivo.relative_to(pasta)
                zip_file.write(arquivo, arcname=arcname)

    buffer.seek(0)
    return buffer.getvalue()


# =========================================================
# 4) LEITURA E PADRONIZAÇÃO DA BASE
# =========================================================
@st.cache_data
def carregar_base(arquivo, sheet_name=0):
    if arquivo is None:
        return None

    df = pd.read_excel(arquivo, sheet_name=sheet_name)
    return df


def padronizar_colunas(df, config):
    colunas = config["colunas"]

    rename_map = {
        colunas["data"]: "data",
        colunas["grupo"]: "grupo",
        colunas["conta"]: "conta",
        colunas["valor"]: "valor",
    }

    if "unidade" in colunas:
        rename_map[colunas["unidade"]] = "unidade"

    df = df.rename(columns=rename_map)

    colunas_necessarias = ["data", "grupo", "conta", "valor"]
    faltantes = [c for c in colunas_necessarias if c not in df.columns]
    if faltantes:
        raise ValueError(f"As seguintes colunas padronizadas não foram encontradas: {faltantes}")

    if "unidade" not in df.columns:
        df["unidade"] = "Consolidado"

    return df


def padronizar_dados(df, config):
    df = df.copy()

    df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    df["mes_formatado"] = gerar_rotulo_mes(df["data"])

    df["grupo"] = df["grupo"].astype(str).str.strip()
    df["conta"] = df["conta"].astype(str).str.strip()
    df["unidade"] = df["unidade"].astype(str).str.strip()

    df["grupo_padrao"] = df["grupo"].replace(config["mapa_grupos"])

    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")

    mask_neg = df["grupo_padrao"].isin(config["grupos_negativos"])
    df.loc[mask_neg, "valor"] = -df.loc[mask_neg, "valor"].abs()

    mask_pos = df["grupo_padrao"] == config["linha_receita_base_av"]
    df.loc[mask_pos, "valor"] = df.loc[mask_pos, "valor"].abs()

    return df


# =========================================================
# 5) MONTAGEM DA DRE
# =========================================================
def serie_grupo(df, nome_grupo):
    return (
        df[df["grupo_padrao"] == nome_grupo]
        .groupby("data")["valor"]
        .sum()
    )


def montar_dre_vertical(df, config):
    dre = {}

    for item in config["estrutura_dre"]:
        nome = item["nome"]

        if item["tipo"] == "grupo":
            dre[nome] = serie_grupo(df, item["origem"])

        elif item["tipo"] == "formula":
            componentes = item["formula"]
            serie_resultado = None

            for comp in componentes:
                if comp not in dre:
                    raise ValueError(f"A fórmula de '{nome}' depende de '{comp}', mas essa linha ainda não foi criada.")
                if serie_resultado is None:
                    serie_resultado = dre[comp].copy()
                else:
                    serie_resultado = serie_resultado.add(dre[comp], fill_value=0)

            dre[nome] = serie_resultado

    dre_df = pd.DataFrame(dre)
    return dre_df


def renomear_colunas_mes(dre_df, df_padronizado):
    mapa_mes = (
        df_padronizado[["data", "mes_formatado"]]
        .drop_duplicates()
        .sort_values("data")
        .set_index("data")["mes_formatado"]
        .to_dict()
    )

    dre_df = dre_df.sort_index()
    dre_df.index = [mapa_mes.get(i, str(i)) for i in dre_df.index]
    return dre_df


# =========================================================
# 6) TABELA DRE + AV + AH + TOTAL ANUAL
# =========================================================
def montar_dre_analitica(dre_mensal, linha_receita_base="Receita Bruta"):
    dre_base = dre_mensal.T.copy()
    dre_base.insert(0, "Descrição", dre_base.index)
    dre_base = dre_base.reset_index(drop=True)

    colunas_meses = [c for c in dre_base.columns if c != "Descrição"]
    dre_analise = dre_base.copy()

    for mes in colunas_meses:
        receita_mes = dre_base.loc[dre_base["Descrição"] == linha_receita_base, mes]
        receita_mes = receita_mes.values[0] if len(receita_mes) else None

        av_col = f"{mes} AV (%)"
        if receita_mes is None or pd.isna(receita_mes) or receita_mes == 0:
            dre_analise[av_col] = pd.NA
        else:
            dre_analise[av_col] = dre_base[mes] / receita_mes * 100

    for i in range(1, len(colunas_meses)):
        mes_atual = colunas_meses[i]
        mes_anterior = colunas_meses[i - 1]
        ah_col = f"{mes_atual} AH (%)"

        base_ant = dre_base[mes_anterior]
        dre_analise[ah_col] = pd.NA

        mask_ok = base_ant.notna() & (base_ant != 0)
        dre_analise.loc[mask_ok, ah_col] = (
            (dre_base.loc[mask_ok, mes_atual] - dre_base.loc[mask_ok, mes_anterior])
            / dre_base.loc[mask_ok, mes_anterior]
            * 100
        )

    nova_ordem = ["Descrição"]
    for mes in colunas_meses:
        nova_ordem.append(mes)

        av_col = f"{mes} AV (%)"
        if av_col in dre_analise.columns:
            nova_ordem.append(av_col)

        ah_col = f"{mes} AH (%)"
        if ah_col in dre_analise.columns:
            nova_ordem.append(ah_col)

    dre_analise = dre_analise[nova_ordem]

    dre_base["TOTAL_ANO"] = dre_base[colunas_meses].sum(axis=1)

    receita_total_ano = dre_base.loc[
        dre_base["Descrição"] == linha_receita_base, "TOTAL_ANO"
    ].values[0]

    dre_base["AV_TOTAL (%)"] = (
        dre_base["TOTAL_ANO"].abs() / abs(receita_total_ano) * 100
        if receita_total_ano not in [0, None] and not pd.isna(receita_total_ano)
        else pd.NA
    )

    dre_analise["TOTAL_ANO"] = dre_base["TOTAL_ANO"].values
    dre_analise["AV_TOTAL (%)"] = dre_base["AV_TOTAL (%)"].values

    return dre_analise, colunas_meses


def aplicar_estilo_dre(dre_analise, colunas_meses):
    colunas_moeda = [c for c in dre_analise.columns if c in colunas_meses or c == "TOTAL_ANO"]
    colunas_percentuais = [
        c for c in dre_analise.columns
        if "AV (%)" in c or "AH (%)" in c or c == "AV_TOTAL (%)"
    ]

    styler = (
        dre_analise
        .style
        .applymap(estilo_financeiro, subset=[c for c in dre_analise.columns if c != "Descrição"])
        .format({
            **{c: formato_contabil for c in colunas_moeda},
            **{c: formato_percentual for c in colunas_percentuais}
        })
    )

    return styler


# =========================================================
# 7) GRÁFICOS
# =========================================================
def grafico_pizza_grupo(df, grupo_padrao, titulo):
    base = df[df["grupo_padrao"] == grupo_padrao].copy()
    if base.empty:
        return None

    agg = base.groupby("conta", as_index=False)["valor"].sum()
    agg["valor_abs"] = agg["valor"].abs()
    agg = agg[agg["valor_abs"] > 0]

    if agg.empty:
        return None

    fig = px.pie(
        agg,
        names="conta",
        values="valor_abs",
        title=titulo,
        hole=0.35
    )
    fig.update_traces(
        textinfo="none",
        hovertemplate="%{label}: R$ %{value:,.2f} (<b>%{percent}</b>)"
    )
    return fig


# =========================================================
# 8) PROCESSAMENTO POR RECORTE
# =========================================================
def processar_base(df_filtrado, config):
    if df_filtrado.empty:
        return None

    dre_vertical = montar_dre_vertical(df_filtrado, config)
    dre_mensal = renomear_colunas_mes(dre_vertical, df_filtrado)

    dre_analise, colunas_meses = montar_dre_analitica(
        dre_mensal,
        linha_receita_base=config["linha_receita_base_av"]
    )
    styler = aplicar_estilo_dre(dre_analise, colunas_meses)

    return {
        "df": df_filtrado,
        "dre_vertical": dre_vertical,
        "dre_mensal": dre_mensal,
        "dre_analise": dre_analise,
        "colunas_meses": colunas_meses,
        "styler": styler
    }


# =========================================================
# 9) FUNÇÕES DE RENDERIZAÇÃO
# =========================================================
def render_dashboard(dados, titulo="Dashboard"):
    if dados is None:
        st.warning(f"Sem dados para {titulo}.")
        return

    df_base = dados["df"]
    dre_mensal = dados["dre_mensal"]

    base_plot = dre_mensal.copy()

    for col in ["Receita Bruta", "Margem de Contribuição", "Resultado Operacional", "Resultado Líquido"]:
        if col in base_plot.columns:
            base_plot[f"{col}_MM"] = mm_cumulativa(base_plot[col])

    base_plot = base_plot.reset_index().rename(columns={"index": "MES"})
    base_plot["ordem"] = range(len(base_plot))

    st.subheader(f"📊 {titulo}")

    st.subheader("📈 Receita Bruta")
    if "Receita Bruta" in base_plot.columns:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=base_plot["MES"], y=base_plot["Receita Bruta"],
            mode="lines+markers", name="Receita Bruta"
        ))
        fig.add_trace(go.Scatter(
            x=base_plot["MES"], y=base_plot["Receita Bruta_MM"],
            mode="lines+markers", name="Receita Bruta (MM cumulativa)"
        ))
        fig.update_layout(
            hovermode="x unified",
            xaxis_title="Mês",
            yaxis_title="R$",
            legend_title=""
        )
        fig.update_traces(hovertemplate="R$ %{y:,.2f}")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Composição da Margem de Contribuição")
    col1, col2 = st.columns(2)

    with col1:
        if all(col in base_plot.columns for col in ["Receita Bruta", "(-) Deduções", "(-) Custos Variáveis", "Margem de Contribuição"]):
            fig_mc = go.Figure()
            fig_mc.add_bar(x=base_plot["MES"], y=base_plot["Receita Bruta"], name="Receita Bruta")
            fig_mc.add_bar(x=base_plot["MES"], y=base_plot["(-) Deduções"], name="(-) Deduções")
            fig_mc.add_bar(x=base_plot["MES"], y=base_plot["(-) Custos Variáveis"], name="(-) Custos Variáveis")
            fig_mc.add_trace(go.Scatter(
                x=base_plot["MES"], y=base_plot["Margem de Contribuição"],
                mode="lines+markers", name="Margem de Contribuição"
            ))
            fig_mc.add_trace(go.Scatter(
                x=base_plot["MES"], y=base_plot["Margem de Contribuição_MM"],
                mode="lines+markers", name="Margem (MM cumulativa)"
            ))
            fig_mc.update_layout(
                barmode="relative",
                title="📊 Margem de Contribuição - Composição",
                xaxis_title="Mês",
                yaxis_title="R$",
                hovermode="x unified"
            )
            fig_mc.update_traces(hovertemplate="R$ %{y:,.2f}")
            st.plotly_chart(fig_mc, use_container_width=True)

    with col2:
        fig_pie = grafico_pizza_grupo(df_base, "Custos Variáveis", "Distribuição dos Custos/Despesas Variáveis")
        if fig_pie:
            st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Composição do Resultado Operacional")
    col1, col2 = st.columns(2)

    with col1:
        if all(col in base_plot.columns for col in ["Margem de Contribuição", "Custos / Despesas", "Resultado Operacional"]):
            fig_ro = go.Figure()
            fig_ro.add_bar(x=base_plot["MES"], y=base_plot["Margem de Contribuição"], name="Margem de Contribuição")
            fig_ro.add_bar(x=base_plot["MES"], y=base_plot["Custos / Despesas"], name="Custos / Despesas")
            fig_ro.add_trace(go.Scatter(
                x=base_plot["MES"], y=base_plot["Resultado Operacional"],
                mode="lines+markers", name="Resultado Operacional"
            ))
            fig_ro.add_trace(go.Scatter(
                x=base_plot["MES"], y=base_plot["Resultado Operacional_MM"],
                mode="lines+markers", name="Resultado Operacional (MM cumulativa)"
            ))
            fig_ro.update_layout(
                barmode="relative",
                title="📊 Resultado Operacional - Composição",
                xaxis_title="Mês",
                yaxis_title="R$",
                hovermode="x unified"
            )
            fig_ro.update_traces(hovertemplate="R$ %{y:,.2f}")
            st.plotly_chart(fig_ro, use_container_width=True)

    with col2:
        fig_pie = grafico_pizza_grupo(df_base, "Custos Fixos", "Distribuição de Custos / Despesas")
        if fig_pie:
            st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Composição do Resultado Líquido")
    col1, col2 = st.columns(2)

    with col1:
        if all(col in base_plot.columns for col in ["Resultado Operacional", "Antecipações e Retiradas de Lucros", "Resultado Líquido"]):
            fig_rl = go.Figure()
            fig_rl.add_bar(x=base_plot["MES"], y=base_plot["Resultado Operacional"], name="Resultado Operacional")
            fig_rl.add_bar(x=base_plot["MES"], y=base_plot["Antecipações e Retiradas de Lucros"], name="Antecipações e Retiradas de Lucros")
            fig_rl.add_trace(go.Scatter(
                x=base_plot["MES"], y=base_plot["Resultado Líquido"],
                mode="lines+markers", name="Resultado Líquido"
            ))
            fig_rl.add_trace(go.Scatter(
                x=base_plot["MES"], y=base_plot["Resultado Líquido_MM"],
                mode="lines+markers", name="Resultado Líquido (MM cumulativa)"
            ))
            fig_rl.update_layout(
                barmode="relative",
                title="📊 Resultado Líquido - Composição",
                xaxis_title="Mês",
                yaxis_title="R$",
                hovermode="x unified"
            )
            fig_rl.update_traces(hovertemplate="R$ %{y:,.2f}")
            st.plotly_chart(fig_rl, use_container_width=True)

    with col2:
        fig_pie = grafico_pizza_grupo(
            df_base,
            "Antecipações e Retiradas de Lucros",
            "Distribuição das Antecipações e Retiradas de Lucros"
        )
        if fig_pie:
            st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("📈 Evolução: Receita Bruta, Resultado Operacional e Saldo Operacional")
    if all(col in base_plot.columns for col in ["Receita Bruta", "Resultado Operacional", "Saldo Operacional"]):
        fig_evolucao = go.Figure()
        fig_evolucao.add_bar(x=base_plot["MES"], y=base_plot["Receita Bruta"], name="Receita Bruta")
        fig_evolucao.add_trace(go.Scatter(
            x=base_plot["MES"], y=base_plot["Resultado Operacional"],
            mode="lines+markers", name="Resultado Operacional"
        ))
        fig_evolucao.add_trace(go.Scatter(
            x=base_plot["MES"], y=base_plot["Saldo Operacional"],
            mode="lines+markers", name="Saldo Operacional"
        ))
        fig_evolucao.update_layout(
            title="📊 Receita Bruta, Resultado Operacional e Saldo Operacional",
            xaxis_title="Mês",
            yaxis_title="R$",
            hovermode="x unified",
            barmode="overlay"
        )
        fig_evolucao.update_traces(hovertemplate="R$ %{y:,.2f}")
        st.plotly_chart(fig_evolucao, use_container_width=True)


def render_demonstrativo(dados, titulo="Demonstrativo"):
    if dados is None:
        st.warning(f"Sem dados para {titulo}.")
        return

    df_base = dados["df"]
    dre_analise = dados["dre_analise"]
    styler = dados["styler"]

    st.subheader(f"📊 {titulo}")
    st.markdown("---")
    st.subheader("📊 Resumo Anual")

    dre_anual = dre_analise[["Descrição", "TOTAL_ANO", "AV_TOTAL (%)"]].copy()
    dre_anual = dre_anual.rename(columns={
        "TOTAL_ANO": "Total Ano",
        "AV_TOTAL (%)": "AV (%)"
    })

    styler_anual = (
        dre_anual
        .style
        .applymap(estilo_financeiro, subset=["Total Ano"])
        .format({
            "Total Ano": formato_contabil,
            "AV (%)": formato_percentual
        })
    )

    st.dataframe(styler_anual, use_container_width=True, hide_index=True)

    st.subheader("📊 Demonstração do Resultado (DRE) - Mensal")
    st.dataframe(styler, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📊 Detalhamento por Grupo")

    lista_grupos = sorted(df_base["grupo_padrao"].dropna().unique().tolist())
    grupo_escolhido = st.selectbox(
        f"Selecione o Grupo - {titulo}",
        lista_grupos,
        key=f"grupo_{titulo}"
    )

    df_g = df_base[df_base["grupo_padrao"] == grupo_escolhido].copy()

    if df_g.empty:
        st.info("Não há dados para esse grupo.")
    else:
        grupo_mensal = (
            df_g.groupby("data", as_index=False)["valor"]
            .sum()
            .sort_values("data")
        )

        grupo_mensal["mes_label"] = gerar_rotulo_mes(pd.to_datetime(grupo_mensal["data"]))

        fig_grupo = go.Figure()
        fig_grupo.add_bar(
            x=grupo_mensal["mes_label"],
            y=grupo_mensal["valor"].abs()
        )
        fig_grupo.update_layout(
            title=f"Evolução Mensal (Grupo) - {grupo_escolhido}",
            xaxis_title="Mês",
            yaxis_title="R$",
            hovermode="x unified",
            showlegend=False
        )
        fig_grupo.update_traces(hovertemplate="R$ %{y:,.2f}")
        st.plotly_chart(fig_grupo, use_container_width=True)

        st.markdown("### 📈 Evolução Histórica das Contas Específicas")

        base_contas = (
            df_g.groupby(["data", "conta"], as_index=False)["valor"]
            .sum()
            .sort_values("data")
        )
        base_contas["mes_label"] = gerar_rotulo_mes(pd.to_datetime(base_contas["data"]))

        contas_disponiveis = sorted(base_contas["conta"].dropna().unique().tolist())

        top5 = (
            base_contas.assign(valor_abs=base_contas["valor"].abs())
            .groupby("conta", as_index=False)["valor_abs"].sum()
            .sort_values("valor_abs", ascending=False)
            .head(5)["conta"]
            .tolist()
        )

        contas_escolhidas = st.multiselect(
            f"Selecione as contas específicas - {titulo}",
            options=contas_disponiveis,
            default=top5,
            key=f"contas_{titulo}"
        )

        if not contas_escolhidas:
            st.info("Selecione pelo menos 1 conta para exibir o gráfico.")
        else:
            df_plot = base_contas[base_contas["conta"].isin(contas_escolhidas)].copy()
            df_plot["valor_plot"] = df_plot["valor"].abs()

            fig_contas = px.line(
                df_plot,
                x="mes_label",
                y="valor_plot",
                color="conta",
                markers=True,
                labels={
                    "mes_label": "Mês",
                    "valor_plot": "R$",
                    "conta": "Conta"
                },
                title=f"Evolução Mensal por Conta — {grupo_escolhido}"
            )
            fig_contas.update_layout(
                hovermode="x unified",
                legend_title_text=""
            )
            fig_contas.update_traces(hovertemplate="R$ %{y:,.2f}")
            st.plotly_chart(fig_contas, use_container_width=True)


# =========================================================
# FUNÇÃO DE DOWNLOADS
# =========================================================
def render_downloads():
    st.subheader("📥 Central de Arquivos")
    st.caption("Baixe o pacote de arquivos entregues pela Focus.")

    caminho_zip = CONFIG["downloads"]["arquivo_zip"]

    if not os.path.exists(caminho_zip):
        st.info("O arquivo ZIP não está disponível neste ambiente.")
        st.write("No ambiente online, use esta área apenas se o ZIP estiver hospedado junto ao projeto.")
        return

    with open(caminho_zip, "rb") as f:
        st.download_button(
            label="⬇️ Baixar arquivos entregues (.zip)",
            data=f.read(),
            file_name="Focus - Arquivos entregues.zip",
            mime="application/zip"
        )


# =========================================================
# 10) PROCESSAMENTO PRINCIPAL
# =========================================================
try:
    df_raw = carregar_base(
        arquivo_upload,
        sheet_name=CONFIG["arquivo"]["sheet_name"]
    )

    if df_raw is None:
        if menu == "Downloads":
            render_downloads()
            st.stop()

        st.info("Envie a base financeira no menu lateral para iniciar o dashboard.")
        st.stop()

    df = padronizar_colunas(df_raw, CONFIG)
    df = padronizar_dados(df, CONFIG)

    dados_consolidado = processar_base(df, CONFIG)

    dados_focus_ic = processar_base(
        df[df["unidade"].str.upper().str.strip() == "FOCUS IC"].copy(),
        CONFIG
    )

    dados_focus_ad = processar_base(
        df[df["unidade"].str.upper().str.strip() == "FOCUS AD"].copy(),
        CONFIG
    )

except Exception as e:
    st.error(f"Erro ao processar a base: {e}")
    st.stop()


# =========================================================
# 11) ROTEAMENTO DOS MENUS
# =========================================================
if menu == "Dashboard":
    render_dashboard(dados_consolidado, "Dashboard Consolidado")

elif menu == "Dashboard Focus IC":
    render_dashboard(dados_focus_ic, "Dashboard Focus IC")

elif menu == "Dashboard Focus AD":
    render_dashboard(dados_focus_ad, "Dashboard Focus AD")

elif menu == "Demonstrativo":
    render_demonstrativo(dados_consolidado, "Demonstrativo Consolidado")

elif menu == "Demonstrativo Focus IC":
    render_demonstrativo(dados_focus_ic, "Demonstrativo Focus IC")

elif menu == "Demonstrativo Focus AD":
    render_demonstrativo(dados_focus_ad, "Demonstrativo Focus AD")

elif menu == "Downloads":
    render_downloads()
    