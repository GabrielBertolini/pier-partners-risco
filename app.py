import streamlit as st

# Configuração institucional da página
st.set_page_config(
    page_title="Píer Partners - Sistema de Análise de Risco",
    layout="wide"
)

# Funçao auxiliar de localização monetária PT-BR
def formatar_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ==============================================================================
# ENGINE DE POLÍTICA DE CRÉDITO COMERCIAL
# ==============================================================================
class CreditEngine:
    def __init__(self, preco_m3_combustivel=5000.0):
        # Parametrização base do preço do m³ de combustível
        self.preco_m3 = preco_m3_combustivel

    def calcular_scorecard(self, cliente):
        """Avaliação quantitativa baseada nos pilares de risco corporativo."""
        
        # PILAR 1: Comportamento Histórico Interno (Peso: 30%)
        if cliente['segmento'] == 'B2B' and cliente['atraso_medio_dias'] > 60 and cliente['gatar_frequencia'] == 'Fiança bancária':
            nota_comportamento = 85  
        else:
            fator_frequencia = max(0, 100 - (cliente['atraso_12m'] * 400))
            fator_dias = max(0, 100 - (cliente['atraso_medio_dias'] * 4))
            nota_comportamento = (fator_frequencia * 0.5) + (fator_dias * 0.5)

        # PILAR 2: Liquidez da Garantia (Peso: 20%)
        garantias_pesos = {
            'Fiança bancária': 100, 'Cessão de recebíveis': 85,
            'Penhor de safra + Aval': 90, 'Penhor de safra': 75,
            'Aval dos sócios': 40, 'Nenhuma': 0
        }
        nota_garantia = garantias_pesos.get(cliente['garantia'], 0)

        # PILAR 3: Exposição de Mercado / Bureau (Peso: 20%)
        if cliente['restritivos']:
            nota_bureau = 0
        else:
            bureau = cliente['score_bureau']
            if bureau >= 850:
                nota_bureau = 100
            elif bureau >= 750:
                nota_bureau = 85
            elif bureau >= 650:
                nota_bureau = 70
            elif bureau >= 550:
                nota_bureau = 40
            else:
                nota_bureau = 10

        # PILAR 4: Enquadramento de Segmento (Peso: 15%)
        segmento_pesos = {
            'Bandeirado': 100, 'B2B': 80, 'TRR': 70, 'Spot / bandeira branca': 40
        }
        nota_segmento = segmento_pesos.get(cliente['segmento'], 40)
        if cliente['relacionamento_meses'] > 24:
            nota_segmento = min(100, nota_segmento + 10)

        # PILAR 5: Capacidade Financeira (Peso: 15%)
        exposicao_solicitada = max(cliente['limite_solicitado'], cliente['limite_atual'])
        if cliente['compras_medias'] <= 0:
            nota_capacidade = 0
        else:
            cobertura = cliente['compras_medias'] / max(exposicao_solicitada, 1)
            if cobertura >= 4:
                nota_capacidade = 100
            elif cobertura >= 3:
                nota_capacidade = 85
            elif cobertura >= 2:
                nota_capacidade = 70
            elif cobertura >= 1:
                nota_capacidade = 50
            else:
                nota_capacidade = 20

        # Penalização por prazo incompatível com comportamento de liquidação
        penalidade_prazo = 0
        if cliente['prazo_solicitado'] == 28 and cliente['atraso_medio_dias'] > 15:
            penalidade_prazo = 10
        elif cliente['prazo_solicitado'] >= 21 and cliente['atraso_medio_dias'] > 20:
            penalidade_prazo = 15

        # Cálculo do Score Final Ponderado
        score_final = (
            (nota_comportamento * 0.30) +
            (nota_garantia * 0.20) +
            (nota_bureau * 0.20) +
            (nota_segmento * 0.15) +
            (nota_capacidade * 0.15)
        )
        
        score_final -= penalidade_prazo
        score_final = max(0, min(100, score_final))
        
        return round(score_final, 1)

    def analisar_credito(self, cliente):
        """Aplica filtros de governança e calcula a alocação ótima de limite."""
        score = self.calcular_scorecard(cliente)
        
        # Segmentação por Tiers de Risco Corporativo
        if score >= 75:
            tier, k_fator = "Tier A - Risco Baixo (Recomendado)", 1.2
        elif score >= 55:
            tier, k_fator = "Tier B - Risco Moderado (Operacional)", 1.0
        elif score >= 40:
            tier, k_fator = "Tier C - Risco Elevado (Em Observação)", 0.5
        else:
            tier, k_fator = "Tier D - Risco Crítico (Restrito)", 0.0

        # Alerta de Risco de Concentração Exógeno
        alerta_concentracao = False
        if cliente['limite_solicitado'] > 2000000:
            alerta_concentracao = True

        motivo_trava = None
        
        # Filtro de Inconsistência Cadastral (Caso C08)
        if cliente.get('obs_inconsistencia', False):
            tier, k_fator = "Tier C - Risco Elevado (Em Observação)", 0.5
            motivo_trava = "Demonstrações financeiras com indícios de inconsistência estrutural."
            
        # Filtro de Cold Start (Caso C05)
        if cliente['relacionamento_meses'] <= 3 and cliente['compras_medias'] == 0:
            tier, k_fator = "Tier C - Risco Elevado (Em Observação)", 0.0
            motivo_trava = "Histórico operacional insuficiente e ausência de balanço patrimonial."

        # Filtro de Restritivos Judiciais/Comerciais (Caso C07)
        if cliente['restritivos']:
            tier, k_fator = "Tier D - Risco Crítico (Restrito)", 0.0
            motivo_trava = "Presença de restritivos fiscais ou apontamentos ativos em bureaus."

        # Formula do Limite Dinâmico Comercial
        limite_calculado = (
            cliente['volume_m3']
            * self.preco_m3
            * (cliente['prazo_solicitado'] / 30.0)
            * k_fator
        )

        # Trava de Segurança por Capacidade Financeira Histórica
        if cliente['compras_medias'] > 0:
            teto_por_faturamento = cliente['compras_medias'] * 1.5
            limite_calculado = min(limite_calculado, teto_por_faturamento)

        limite_calculado = round(limite_calculado, -3)

        # Definição do veredito comercial e alocações associadas
        if "Tier A" in tier:
            veredito = "APROVADO INTEGRALMENTE"
            limite_concedido = cliente['limite_solicitado']
            acao = "Cliente preferencial. Liberar alocação de limite conforme solicitado e aplicar política de fidelização."
        elif "Tier B" in tier:
            if cliente['limite_solicitado'] > 2000000:
                veredito = "APROVADO VIA COMITÊ EXECUTIVO"
                limite_concedido = cliente['limite_solicitado']
                acao = "Risco de concentração elevado. Exigir auditoria periódica e monitoramento da carteira de recebíveis."
            else:
                veredito = "APROVADO SOB CONDIÇÃO"
                limite_concedido = min(cliente['limite_solicitado'], limite_calculado)
                acao = f"Liberação de limite condicionada à formalização e registro da garantia de {cliente['garantia']}."
        elif "Tier C" in tier:
            veredito = "EXPOSIÇÃO ADICIONAL REPROVADA"
            # CORREÇÃO DO PARADOXO DE CRÉDITO: Garante que o risco mitigado respeite o menor valor do teto
            limite_concedido = min(cliente['limite_atual'], limite_calculado)
            acao = f"RETENÇÃO OPERACIONAL: {motivo_trava} " if motivo_trava else ""
            acao += f"Giro de segurança avaliado em {formatar_brl(limite_calculado)}. Reduzir exposição e reter limite teto em {formatar_brl(limite_concedido)} pendente de auditoria de campo."
        else:
            veredito = "SUSPENSÃO DE CRÉDITO COMERCIAL"
            if cliente['atraso_12m'] > 0.10:
                limite_concedido = 0.0
                acao = "Régua de Cobrança Nível Máximo: Reduzir exposição a zero. Migrar operação para regime de pagamento antecipado."
            else:
                limite_concedido = max(0.0, round(cliente['limite_atual'] * 0.6, -3))
                acao = f"Curva de degradação financeira identificada. Reduzir teto de exposição atual para mitigação de perda latente."

        if alerta_concentracao:
            acao += "\n\nALERTA: Cliente classificado como potencial risco de concentração da carteira."

        fatores = []
        if cliente['relacionamento_meses'] > 24:
            fatores.append("Relacionamento consolidado junto à distribuidora.")
        if cliente['score_bureau'] >= 750:
            fatores.append("Score de bureau de crédito externo robusto.")
        if cliente['garantia'] in ['Fiança bancária', 'Cessão de recebíveis', 'Penhor de safra + Aval']:
            fatores.append("Estrutura de garantias/colaterais de alta liquidez.")
        if cliente['atraso_12m'] > 0.08:
            fatores.append("Histórico recente com frequência de atraso relevante nos últimos 12 meses.")
        if cliente['restritivos']:
            fatores.append("Apontamentos restritivos ativos detectados em cadastros de proteção ao crédito.")

        return {
            "score": score, 
            "tier": tier, 
            "veredito": veredito, 
            "limite_concedido": limite_concedido, 
            "acao_comercial": acao,
            "fatores": fatores
        }

# Base de Dados Fictícia da Carteira para Demonstração em Apresentação
carteira_mock = {
    "Selecione um Cliente para Análise": {"id": "NÚM", "nome": "", "segmento": "Bandeirado", "relacionamento_meses": 12, "compras_medias": 100000, "volume_m3": 20, "prazo_solicitado": 14, "limite_atual": 100000, "limite_solicitado": 150000, "atraso_12m": 0.0, "atraso_medio_dias": 0, "score_bureau": 700, "restritivos": False, "garantia": "Nenhuma", "obs_inconsistencia": False},
    "C01 - Posto Bandeira Aurora": {"id": "C01", "nome": "Posto Bandeira Aurora", "segmento": "Bandeirado", "relacionamento_meses": 96, "compras_medias": 420000, "volume_m3": 95, "prazo_solicitado": 21, "limite_atual": 350000, "limite_solicitado": 500000, "atraso_12m": 0.02, "atraso_medio_dias": 3, "score_bureau": 880, "restritivos": False, "garantia": "Aval dos sócios", "obs_inconsistencia": False},
    "C05 - Posto Novo Horizonte (Cold Start)": {"id": "C05", "nome": "Posto Novo Horizonte", "segmento": "Spot / bandeira branca", "relacionamento_meses": 3, "compras_medias": 0, "volume_m3": 35, "prazo_solicitado": 14, "limite_atual": 0, "limite_solicitado": 250000, "atraso_12m": 0.0, "atraso_medio_dias": 0, "score_bureau": 690, "restritivos": False, "garantia": "Aval dos sócios", "obs_inconsistencia": False},
    "C06 - Rede Movência (Concentração)": {"id": "C06", "nome": "Rede Movência", "segmento": "Bandeirado", "relacionamento_meses": 84, "compras_medias": 2400000, "volume_m3": 560, "prazo_solicitado": 28, "limite_atual": 1800000, "limite_solicitado": 2600000, "atraso_12m": 0.03, "atraso_medio_dias": 5, "score_bureau": 830, "restritivos": False, "garantia": "Cessão de recebíveis", "obs_inconsistencia": False},
    "C08 - Transportes Coqueiros (Inconsistência)": {"id": "C08", "nome": "Transportes Coqueiros", "segmento": "B2B", "relacionamento_meses": 22, "compras_medias": 360000, "volume_m3": 90, "prazo_solicitado": 28, "limite_atual": 200000, "limite_solicitado": 600000, "atraso_12m": 0.07, "atraso_medio_dias": 12, "score_bureau": 660, "restritivos": False, "garantia": "Nenhuma", "obs_inconsistencia": True},
    "C12 - Frota CidadeLog (Descasamento de Caixa)": {"id": "C12", "nome": "Frota CidadeLog", "segmento": "B2B", "relacionamento_meses": 26, "compras_medias": 290000, "volume_m3": 72, "prazo_solicitado": 28, "limite_atual": 180000, "limite_solicitado": 380000, "atraso_12m": 0.05, "atraso_medio_dias": 77, "score_bureau": 750, "restritivos": False, "garantia": "Fiança bancária", "obs_inconsistencia": False}
}

# ==============================================================================
# RENDERIZAÇÃO DA INTERFACE INSTITUCIONAL
# ==============================================================================
st.title("Píer Partners — Sistema de Análise de Crédito Corporativo")
st.markdown("### Distribuição de Combustíveis e Análise de Portfólio")
st.markdown("---")

st.markdown("#### Simulação Comercial e Carga de Dados")
selecao = st.selectbox("Selecione um proponente para preenchimento automatizado dos parâmetros da política:", list(carteira_mock.keys()))
dados_base = carteira_mock[selecao]

col_inputs, col_outputs = st.columns([2, 2], gap="large")

with col_inputs:
    st.markdown("#### Parâmetros Cadastrais e Operacionais")
    nome = st.text_input("Razão Social do Proponente:", value=dados_base["nome"])
    
    c1, c2 = st.columns(2)
    with c1:
        segmento = st.selectbox("Segmento de Atuação:", ["Bandeirado", "Spot / bandeira branca", "TRR", "B2B"], index=["Bandeirado", "Spot / bandeira branca", "TRR", "B2B"].index(dados_base["segmento"]))
        relacionamento = st.number_input("Tempo de Relacionamento (meses):", min_value=0, value=dados_base["relacionamento_meses"])
        compras_medias = st.number_input("Média Mensal de Faturamento com a Distribuidora (R$):", min_value=0.0, value=float(dados_base["compras_medias"]), step=10000.0)
        volume_m3 = st.number_input("Volume Projetado ou Contratual (m³/mês):", min_value=0, value=dados_base["volume_m3"])
    with c2:
        prazo = st.selectbox("Prazo de Faturamento Solicitado (Dias):", [0, 14, 21, 28], index=[0, 14, 21, 28].index(dados_base["prazo_solicitado"]))
        limite_atual = st.number_input("Limite de Crédito Ativo (R$):", min_value=0.0, value=float(dados_base["limite_atual"]), step=10000.0)
        limite_solicitado = st.number_input("Limite de Crédito Pleiteado (R$):", min_value=0.0, value=float(dados_base["limite_solicitado"]), step=10000.0)
        garantia = st.selectbox("Colateral / Garantia Ofertada:", ['Fiança bancária', 'Cessão de recebíveis', 'Penhor de safra + Aval', 'Penhor de safra', 'Aval dos sócios', 'Nenhuma'], index=['Fiança bancária', 'Cessão de recebíveis', 'Penhor de safra + Aval', 'Penhor de safra', 'Aval dos sócios', 'Nenhuma'].index(dados_base["garantia"]))

    st.markdown("#### Indicadores de Comportamento Financeiro")
    c3, c4 = st.columns(2)
    with c3:
        atraso_12m = st.slider("Frequência de Atrasos nos Últimos 12 Meses (Proporção):", 0.0, 1.0, float(dados_base["atraso_12m"]), step=0.01, format="%.2f")
        atraso_medio = st.number_input("Atraso Médio de Liquidação (Dias):", min_value=0, value=dados_base["atraso_medio_dias"])
    with c4:
        score_bureau = st.slider("Score de Crédito Excluído (Bureaus de Mercado):", 0, 1000, int(dados_base["score_bureau"]))
        restritivo = st.checkbox("Restritivo Ativo (Protestos, Ações Judiciais ou Negativações)", value=dados_base["restritivos"])
        inconsistencia = st.checkbox("Inconsistência cadastral identificada nas demonstrações contábeis", value=dados_base.get("obs_inconsistencia", False))

# Processamento da lógica
cliente_payload = {
    "segmento": segmento, "relacionamento_meses": relacionamento, "compras_medias": compras_medias,
    "volume_m3": volume_m3, "prazo_solicitado": prazo, "limite_atual": limite_atual,
    "limite_solicitado": limite_solicitado, "atraso_12m": atraso_12m, "atraso_medio_dias": atraso_medio,
    "score_bureau": score_bureau, "restritivos": restritivo, "garantia": garantia, "obs_inconsistencia": inconsistencia
}

engine = CreditEngine()
resultado = engine.analisar_credito(cliente_payload)

with col_outputs:
    st.markdown("#### Parecer Técnico e Resultados do Modelo")
    
    st.markdown("##### Métricas Quantitativas de Risco")
    m1, m2 = st.columns(2)
    with m1:
        st.metric(label="Pontuação do Scorecard Interno", value=f"{resultado['score']} / 100")
    with m2:
        st.write("**Classificação do Portfólio:**")
        st.markdown(
            f"<div style='font-family: monospace; background-color: rgba(128, 128, 128, 0.15); color: inherit; padding: 8px 12px; border-radius: 4px; font-size: 14px; border: 1px solid rgba(128, 128, 128, 0.3); font-weight: bold;'>{resultado['tier']}</div>", 
            unsafe_allow_html=True
        )

    st.markdown("---")
    
    st.markdown("##### Principais Fatores da Decisão")
    if resultado["fatores"]:
        for f in resultado["fatores"]:
            st.markdown(f"• {f}")
    else:
        st.markdown("• *Nenhum fator crítico de risco ou destaque positivo mapeado.*")

    st.markdown("---")
    st.markdown("##### Deliberação de Crédito Comercial")
    
    st.markdown(f"**Veredito de Risco:** {resultado['veredito']}")
    # CORREÇÃO DO SEPARADOR DE MOEDA LOCAL (BR)
    st.metric(label="Limite Máximo Recomendado (Alocação Segura)", value=formatar_brl(resultado['limite_concedido']))
    
    st.markdown("##### Diretriz Operacional de Cobrança e Gestão de Conta")
    st.info(resultado['acao_comercial'])

# ==============================================================================
# DOCUMENTAÇÃO E APRESENTAÇÃO MATEMÁTICA E PRODUTO (SEM EMOJIS)
# ==============================================================================
st.markdown("<br><br><br>", unsafe_allow_html=True)
st.markdown("---")
st.header("Memória de Cálculo e Estratégia de Produto (Apresentação aos Sócios)")
st.markdown("*Consolidação técnica e comercial da inteligência de crédito embarcada no sistema Píer Partners.*")

tab_visao, tab_score, tab_limite, tab_governanca = st.tabs([
    "1. Arquitetura do Produto", 
    "2. Equações do Scorecard", 
    "3. Limite e Trava Patrimonial", 
    "4. Matriz LGD e Casos Práticos"
])

with tab_visao:
    st.subheader("Solução CreditTech de Alta Performance para Combustíveis")
    st.markdown(r"""
    O mercado de distribuição de combustíveis opera sob cenários de volatilidade extrema de preços, margens estreitas e alta frequência transacional. Sistemas de crédito tradicionais ou puramente baseados em balanços anuais falham por falta de agilidade e sensibilidade setorial.
    
    Este produto foi construído sobre uma arquitetura de risco de três camadas, protegendo a liquidez da carteira sem engessar a operação comercial:
    
    1. Camada Quantitativa Dinâmica (Scorecard Histórico + Mercado): Consolida dados de comportamento transacional interno, bureaus e capacidade financeira em uma nota em tempo real.
    2. Camada de Governança e Compliance (Filtros Qualitativos Duros): Trava proponentes automaticamente em cenários de riscos estruturais (fraude cadastral, colapso financeiro ou restritivos graves).
    3. Camada de Alocação Ótima (Giro Baseado em Volumetria): Calcula a exposição segura baseada na demanda volumétrica projetada, amarrada ao prazo financeiro solicitado.
    """)

with tab_score:
    st.subheader("Formulação Matemática do Scorecard Multicritério")
    st.markdown(r"A nota final de risco do proponente (Score) é modelada através de uma média ponderada sobre 5 pilares estratégicos de dados:")
    
    st.latex(r"""
    \text{Score Base} = (N_{\text{comp}} \times 0.30) + (N_{\text{gar}} \times 0.20) + (N_{\text{bur}} \times 0.20) + (N_{\text{seg}} \times 0.15) + (N_{\text{cap}} \times 0.15)
    """)
    
    st.markdown(r"#### Modelagem Matemática dos Pilares de Entrada ($N$):")
    st.markdown(r"""
    * $N_{\text{comp}}$ (Comportamento Interno - Peso: 30%): Avalia simultaneamente a frequência de inadimplência recente e a severidade temporal média dos atrasos:
        * Fator Frequência: $100 - (\text{atraso\_12m} \times 400)$
        * Fator Dias: $100 - (\text{atraso\_medio\_dias} \times 4)$
        * Cálculo: Média aritmética simples entre os dois fatores ($\frac{Freq + Dias}{2}$).
    * $N_{\text{bur}}$ (Exposição de Mercado - Peso: 20%): Em vez de adotar uma abordagem linear ineficiente, o motor implementa uma Step Function (função descontínua por degraus) para isolar faixas de score externo dos bureaus:
        * Se Bureau $\ge 850 \rightarrow 100 \ \vert\ \ge 750 \rightarrow 85 \ \vert\ \ge 650 \rightarrow 70 \ \vert\ \ge 550 \rightarrow 40 \ \vert\ < 550 \rightarrow 10$
    * $N_{\text{cap}}$ (Capacidade Financeira - Peso: 15%): Novo pilar para mitigar empresas de fachada. Avalia a Razão de Cobertura do faturamento transacional médio frente à exposição de teto demandada:
    """)
    st.latex(r"\text{Razão de Cobertura} = \frac{\text{Compras Médias Mensais}}{\max(\text{Limite Solicitado}, \text{Limite Atual})}")
    st.markdown(r"""
        * Razão $\ge 4 \rightarrow 100 \ \vert\ \ge 3 \rightarrow 85 \ \vert\ \ge 2 \rightarrow 70 \ \vert\ \ge 1 \rightarrow 50 \ \vert\ < 1 \rightarrow 20$
    * $N_{\text{seg}}$ (Segmentação - Peso: 15%): Pontua o risco sistêmico da carteira (Bandeirado: 100, B2B: 80, TRR: 70, Spot: 40). Contas com relacionamento $\ge 24$ meses recebem prêmio de $+10$ pontos de fidelidade.
    """)
    
    st.markdown(r"#### Penalização de Risco de Liquidação Temporal (PMR Implícito):")
    st.markdown(r"Para conter o risco latente de descasamento financeiro de clientes que solicitam prazos longos mas carregam um histórico lento de pagamento, o modelo aplica um vetor de penalidade na nota base:")
    st.latex(r"""
    \text{Penalidade} = \begin{cases} 
    10, & \text{se } \text{Prazo Solicitado} = 28 \text{ dias e } \text{Atraso Médio} > 15 \text{ dias} \\
    15, & \text{se } \text{Prazo Solicitado} \ge 21 \text{ dias e } \text{Atraso Médio} > 20 \text{ dias} 
    \end{cases}
    """)
    st.latex(r"\text{Score Final} = \max(0, \min(100, \text{Score Base} - \text{Penalidade}))")

with tab_limite:
    st.subheader("Arquitetura do Cálculo de Limite Dinâmico Comercial")
    st.markdown(r"Diferente de sistemas legados que concedem crédito estático com base apenas no balanço, nosso motor calcula o limite técnico com base na necessidade real de giro do estoque financiado:")
    
    st.latex(r"""
    \text{Limite Calculado} = \text{Volume (m³)} \times \text{Preço do m³} \times \left(\frac{\text{Prazo Solicitado}}{30}\right) \times k
    """)
    
    st.markdown(r"#### Parametrização do Coeficiente de Apetite Comercial ($k$):")
    st.markdown(r"""
    O fator $k$ calibra a agressividade comercial permitida para cada faixa de risco estruturado (Tiers):
    * Tier A (Score $\ge 75$): $k = 1.2$ (Agressividade estratégica: adiciona 20% de limite sobre a volumetria contratual para capturar market share de clientes excelentes).
    * Tier B (Score $55 \vdash 74$): $k = 1.0$ (Neutralidade operacional: aloca o limite exato do giro de estocagem).
    * Tier C (Score $40 \vdash 54$): $k = 0.5$ (Filtro defensivo: corta a exposição recomendada pela metade).
    * Tier D (Score $< 40$): $k = 0.0$ (Bloqueio total: exposição dinâmica zerada).
    """)
    
    st.markdown(r"#### Mecanismo Hard Cap de Proteção Patrimonial")
    st.markdown(r"Para mitigar projeções de compra fraudulentas ou superestimadas pela força comercial, o sistema confronta o resultado numérico contra a capacidade comprovada do cliente, aplicando uma trava rígida:")
    st.latex(r"""
    \text{Limite Recomendado Final} = \min(\text{Limite Calculado}, \text{Compras Médias Mensais} \times 1.5)
    """)
    st.markdown(r"> **Nota de Produto:** Esta regra garante que nenhuma linha de crédito comercial ativa possa explodir e ultrapassar 150% do histórico consolidado, blindando o caixa do fundo contra alavancagens predatórias.")

with tab_governanca:
    st.subheader("Matriz de Severidade de Perda (LGD) e Alinhamento Comercial (XAI)")
    st.markdown(r"Para dar total clareza aos sócios e mitigar o clássico atrito entre a Mesa de Crédito e o time Comercial, o sistema une regras duras de severidade com explicabilidade de decisões (XAI).")
    
    st.markdown(r"#### 1. Matriz de Colaterais e Liquidez Jurídica")
    st.markdown(r"""
    Os pesos atribuídos no pilar de garantias do scorecard refletem a facilidade de recuperação e execução dos ativos (Loss Given Default):
    * Fiança Bancária (100): Risco caixa de liquidez imediata emitida por instituição financeira de primeira linha.
    * Penhor de Safra + Aval (90): Vinculação real de commodity física atrelada à corresponsabilidade pessoal dos proprietários.
    * Cessão de Recebíveis (85): Fluxo financeiro estruturado, contudo indexado ao risco de performance de terceiros na ponta.
    * Penhor de Safra (75): Boa colateralização em grãos/commodities, exigindo custos de custódia e ritos de tomada física.
    * Aval dos Sócios (40): Baixa liquidez imediata; sujeito a disputas judiciais lentas e risco de desfazimento patrimonial.
    """)
    
    st.markdown(r"#### 2. Casos Práticos de Governança Embarcados")
    st.markdown(r"""
    * Mitigação do Risco de Concentração (Caso C06): Operações com exposição pleiteada acima de R$ 2.000.000,00 disparam alertas sistêmicos em tempo real, forçando a mudança do rito de aprovação para Comitê Executivo e exigindo monitoramento e auditoria periódica de recebíveis.
    * Tratamento de Inconsistência Estrutural (Caso C08): Auditoria de balanço. Indícios de rasuras ou inconsistências cadastrais derrubam o cliente automaticamente para o Tier C, limitando a concessão de crédito comercial.
    * Exceção de Descasamento Público / B2B (Caso C12): Postos e frotas focados em contratos governamentais rotineiramente sofrem com prazos estendidos e atrasos por burocracia do Estado. Se amparado por Fiança Bancária, o motor isola esse ruído operacional e fixa a nota em 85, retendo uma conta altamente lucrativa sem expor a distribuidora ao risco real.
    * Tratamento de Cold Start (Caso C05): Contas novas na distribuidora com tempo de relacionamento $\le 3$ meses e sem histórico de faturamento são bloqueadas de receber limites dinâmicos sem a devida apresentação de colaterais líquidos ou evolução da curva de confiança.
    """)
