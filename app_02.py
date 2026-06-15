import streamlit as st

# Configuração institucional da página
st.set_page_config(
    page_title="Píer Partners: Sistema de Análise de Risco - Gabriel Bertolini",
    layout="wide"
)

# Funçao auxiliar de localização monetária PT-BR
def formatar_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class CreditEngine:
    def __init__(self, preco_m3_combustivel=5000.0):
        # Parametrização base do preço do m³ de combustível
        self.preco_m3 = preco_m3_combustivel

    def calcular_scorecard(self, cliente):
        """Avaliação quantitativa baseada nos pilares de risco corporativo."""
        
        # PILAR 1: Comportamento Histórico Interno (Peso: 30%)
        if cliente['segmento'] == 'B2B' and cliente['atraso_medio_dias'] > 60 and cliente['garantia'] == 'Fiança bancária':
            nota_comportamento = 85  
        else:
            fator_frequencia = max(0, 100 - (cliente['atraso_12m'] * 400))
            fator_dias = max(0, 100 - (cliente['atraso_medio_dias'] * 4))
            nota_comportamento = (fator_frequencia * 0.5) + (fator_dias * 0.5)

        # PILAR 2: Liquidez da Garantia (Peso: 20%)
        g_pesos = {
            'Fiança bancária': 100, 'Cessão de recebíveis': 85,
            'Penhor de safra + Aval': 90, 'Penhor de safra': 75,
            'Aval dos sócios': 40, 'Nenhuma': 0
        }
        nota_garantia = g_pesos.get(cliente['garantia'], 0)

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
        
        # Gatilho de segurança para operações puramente à vista
        if cliente['prazo_solicitado'] == 0:
            return {
                "score": self.calcular_scorecard(cliente),
                "tier": "Operacao de Pronta Entrega (A Vista)",
                "veredito": "PAGAMENTO ANTECIPADO REQUERIDO",
                "limite_concedido": 0.0,
                "acao_comercial": "Pedido configurado sem prazo de faturamento financeiro. Liberar carregamento do produto estritamente apos a confirmacao de PIX ou TED em conta corrente. Esta operacao dispensa a exigencia de colaterais ou garantias por nao reter risco latente de credito.",
                "fatores": ["Operacao comercial estruturada inteiramente a vista."]
            }

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
                if cliente['garantia'] == 'Nenhuma':
                    acao = "Liberação de limite comercial baseada no giro operacional puro. Recomenda-se estruturar colaterais em negociações futuras para expansão do teto de crédito de conta limpa."
                else:
                    acao = f"Liberação de limite condicionada à formalização e registro da garantia de {cliente['garantia']}."
        elif "Tier C" in tier:
            veredito = "EXPOSIÇÃO ADICIONAL REPROVADA"
            limite_concedido = min(cliente['limite_atual'], limite_calculado)
            acao = f"RETENCAO OPERACIONAL: {motivo_trava} " if motivo_trava else ""
            
            txt_calculado = formatar_brl(limite_calculado).replace("$", r"\$")
            txt_concedido = formatar_brl(limite_concedido).replace("$", r"\$")
            
            acao += f"Giro maximo de seguranca calculado em {txt_calculado}. Reduzir exposicao ativa e travar o limite total recomendado em {txt_concedido} pendente de auditoria de campo."
        else:
            veredito = "SUSPENSÃO DE CRÉDITO COMERCIAL"
            if cliente['restritivos'] or cliente['atraso_12m'] > 0.10:
                limite_concedido = 0.0
                acao = "Regua de Cobranca Nivel Maximo: Restritivos ativos ou inadimplencia severa detectada. Bloquear concessao de limite e migrar conta para regime de pagamento antecipado."
            else:
                limite_concedido = min(limite_calculado, max(0.0, round(cliente['limite_atual'] * 0.6, -3)))
                acao = f"Curva de degradacao financeira identificada. Reduzir teto de exposicao atual para mitigacao de perda latente."

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


st.title("Píer Partners: Sistema de Análise de Crédito Corporativo - Gabriel Bertolini")
st.markdown("### Distribuição de Combustíveis e Análise de Portfólio")
st.markdown("---")

st.header("Proposta de Política de Crédito")

# Criação das 5 Abas Oficiais baseadas no Case de Gestão de Operações
tab_secao1, tab_secao2, tab_secao3, tab_secao4, tab_secao5 = st.tabs([
    "1. Matriz de Segmentação", 
    "2. Fontes & Indicadores Preditivos", 
    "3. Cálculo de Limite & Garantias", 
    "4. Alçadas & Régua de Cobrança",
    "5. Estrutura do Scorecard & Tiers"
])

with tab_secao1:
    st.subheader("Seção 1: Diretrizes de Segmentação e Matriz de Risco Setorial")
    st.markdown(r"""
    No mercado brasileiro de distribuição de combustíveis, as operações são caracterizadas por margens de lucro extremamente estreitas, altíssima necessidade de capital de giro e ciclos ágeis de liquidação de caixa. O risco de inadimplência varia drasticamente dependendo do modelo de atuação do cliente final e de seu segmento:

    * **Clientes Bandeirados (Risco Mínimo):** Operam sob contratos de exclusividade de longo prazo. Apresentam a menor volatilidade devido à alta previsibilidade da demanda e à fidelidade contratual forçada. "A análise deve focar em fatores comportamentais e de compliance, especialmente na aderência aos compromissos contratuais e na conformidade dos volumes operacionais previstos.
    * **Clientes Bandeira Branca / Spot (Risco Elevado):** Revendedores independentes sem contratos de exclusividade. Compram estritamente por oportunidade de preço diário. Suas margens são esmagadas para competir no varejo de rua, tornando-os altamente vulneráveis a quebras de caixa repentinas. A análise deve ser defensiva e focada em liquidez e colaterais de rápida execução.
    * **TRRs - Transportadores-Revendedores-Retalhistas (Risco Moderado-Alto):** Atendem principalmente produtores rurais, pequenas empresas e frotas. Seu risco está relacionado à capacidade de manter um fluxo de caixa saudável e uma carteira de clientes ativa. A análise deve avaliar o histórico de pagamentos, a estabilidade das vendas e a capacidade financeira da operação.
    * **Clientes B2B / Consumidores Finais (Risco Alto):** Grandes empresas (indústrias, usinas, transportadoras de grande porte) que consomem o combustível internamente sem revender. O consumo é cativo e altamente previsível porque a frota não pode parar. A análise baseia-se na metodologia de análise de crédito corporativo tradicional via estrutura de balanço patrimonial e demonstração de resultados (EBITDA, alavancagem, liquidez).
    """)

with tab_secao2:
    st.subheader("Seção 2: Fontes Alternativas de Informação e Indicadores Preditivos de Risco")
    st.markdown(r"""
Quando as demonstrações contábeis tradicionais (balanços) não são confiáveis (indícios de dados inflados) ou inexistem (clientes novos em *cold start*), o processo de subscrição e inteligência de risco deve se ancorar em sinais indiretos de capacidade de pagamento:


* **Sinais Indiretos de Validação e Fontes Alternativas:**
    * *Fluxo de Caixa de Cartões:* Permite validar o faturamento real e a movimentação financeira do negócio.
    * *Dados Regulatórios da ANP:* Consulta à situação cadastral e à regularidade operacional do cliente junto aos órgãos reguladores.
    * *Movimentação Operacional:* Análise do volume comercializado para verificar se a atividade observada é compatível com o porte declarado.
    * *Auditoria de Campo:* Visitas presenciais para validar estrutura, operação e capacidade comercial do estabelecimento.

* **Variáveis Mais Preditivas de Inadimplência do Setor:**
    * *Frequência de Atrasos Recentes (12 meses):* Captura a perda recorrência de controle de capital de giro de curto prazo.
    * *Severidade Temporal (Atraso Médio em Dias):* O esticamento sistemático de prazos de liquidação internos sinaliza estresse severo de caixa.
    * *Score de Bureau de Mercado Ajustado:* Essencial para mapear e isolar o endividamento do cliente fora da distribuidora (bancos e protestos em cartórios).
    * *Volatilidade de Margem na Bomba:* A incapacidade do posto independente de repassar altas internacionais de preço da refinaria esmaga sua liquidez em poucos dias.
""")


with tab_secao3:
    st.subheader("Seção 3: Metodologia de Cálculo de Limite e Estrutura de Colaterais (Garantias)")
    st.markdown(r"""
    A concessão de crédito é baseada na real necessidade de giro do cliente, garantindo uma exposição compatível com sua operação e protegendo o caixa da distribuidora.
    """)
    
    st.latex(r"""
    \text{Limite Calculado} = \text{Volume } (m^3) \times \text{Preço do } m^3 \times \left(\frac{\text{Prazo Solicitado}}{30}\right) \times k
    """)
    
    st.markdown(r"""
    * **Coeficiente de Ajuste de Risco ($k$):**
        * *Tier A (Risco Baixo):* $k = 1.2$ (Permite alavancagem de +20% para capturar mercado).
        * *Tier B (Risco Moderado):* $k = 1.0$ (Neutralidade comercial).
        * *Tier C (Risco Elevado):* $k = 0.5$ (Filtro defensivo que corta o teto pela metade).
        * *Tier D (Risco Crítico):* $k = 0.0$ (Bloqueio/Venda à vista).

    * **Mecanismo Hard Cap de Proteção Patrimonial:**
        Para blindar o caixa contra projeções comerciais superestimadas, o sistema aplica uma trava rígida baseada no histórico comprovado:
    """)
    st.latex(r"""
    \text{Limite Recomendado Final} = \min(\text{Limite Calculado},\ \text{Compras Médias Mensais} \times 1.5)
    """)
    st.markdown(r"""
    * **Hierarquia Jurídica de Garantias (Loss Given Default - LGD):**
        * *Fiança Bancária (Peso 100):* Liquidez imediata emitida por bancos de primeira linha, exigida para grandes contas B2B ou frotas governamentais.
    A concessão de crédito é baseada na real necessidade de giro do cliente, garantindo uma exposição compatível com sua operação e protegendo o caixa da distribuidora.
        * *Penhor de Safra + Aval (Peso 90) e Penhor de Safra (Peso 75):*  Garantias reais utilizadas principalmente em clientes com exposição ao agronegócio, agregando proteção patrimonial por meio da vinculação da produção futura e reduzindo a perda potencial em caso de inadimplência.
        * *Cessão de Recebíveis Estruturada (Peso 85):* Domiciliação do fluxo de cartões do posto em favor da distribuidora, interceptando o dinheiro direto na fonte.
        * *Aval dos Sócios (Peso 40):* Amarração jurídica básica para coibir risco moral de pequenas empresas, vinculando o patrimônio dos proprietários.
    """)

with tab_secao4:
    st.subheader("Seção 4: Governança Operacional e Cobrança")
    st.markdown(r"""
A governança de crédito é estruturada em alçadas de aprovação e uma régua de cobrança rígida, garantindo controle de risco ao longo de todo o ciclo da operação.

* **Alçadas de Aprovação:**
    * *Mesa Sistêmica:* Aprova operações até R$ 2.000.000 para clientes Tier A ou B dentro da política padrão.
    * *Comitê Executivo:* Avalia operações acima de R$ 2.000.000 ou casos com risco de concentração relevante.
    * *Diretoria / Conselho:* Responsável por exceções, reestruturações e decisões estratégicas de grande porte.

* **Régua de Cobrança:**
    * *D-2 a D-1:* Lembretes preventivos de vencimento.
    * *D+1:* Cobrança ativa imediata.
    * *D+3:* Bloqueio de novas retiradas de combustível.
    * *D+5:* Protesto e negativação.
    * *D+15:* Início da execução de garantias.

* **Tratamento de Exceções:**
    Contas com característica pública ou B2B podem apresentar atraso técnico de pagamento. Nesses casos, quando houver garantia líquida (ex: fiança bancária), a régua de cobrança pode ser flexibilizada mediante validação de baixo risco de inadimplência real.
""")

with tab_secao5:
    # CORREÇÃO CRÍTICA: Seção 5 reestruturada para funcionar como o elo lógico do sistema inteiro
    st.subheader("Seção 5: Arquitetura do Modelo de Score e Conexão com os Tiers de Risco")
    st.markdown(r"""
    O MVP funciona como o elo integrador de toda a política de crédito. Ele opera em uma estrutura de duas etapas: primeiro, consolida os dados no **Scorecard** quantitativo; segundo, traduz essa pontuação em um **Tier de Risco**, que dita o coeficiente de apetite comercial ($k$) que alimenta o cálculo de limite da Seção 3.

    #### 1. Formulação Matemática do Scorecard (Os Inputs)
    A pontuação base do proponente ($Score$) unifica cinco pilares estratégicos de dados, gerando uma nota de 0 a 100:
    """)
    
    st.latex(r"""
    \text{Score Base} = (N_{\text{comp}} \times 0.30) + (N_{\text{gar}} \times 0.20) + (N_{\text{bur}} \times 0.20) + (N_{\text{seg}} \times 0.15) + (N_{\text{cap}} \times 0.15)
    """)
    
    st.markdown(r"""
    * **$N_{\text{comp}}$ (Comportamento Interno - 30%):** Histórico de atrasos e inadimplência transacional.
    * **$N_{\text{gar}}$ (Liquidez da Garantia - 20%):** Nota de segurança jurídica e velocidade de execução do colateral oferecido.
    * **$N_{\text{bur}}$ (Exposição de Mercado - 20%):** Nota descontínua (*Step Function*) das restrições em bureaus de crédito externos.
    * **$N_{\text{seg}}$ (Segmentação Comercial - 15%):** Risco sistêmico do canal (Bandeirado = 100, B2B = 80, TRR = 70, Spot = 40). Com adicional de +10 pontos para relacionamento > 24 meses.
    * **$N_{\text{cap}}$ (Capacidade Financeira - 15%):** Razão de Cobertura das compras transacionais contra o limite pleiteado, utilizada para avaliar se o volume operacional do cliente é suficiente para sustentar a exposição de crédito, $\text{Cobertura} = \frac{\text{Compras médias mensais}}{\max(\text{limite solicitado}, \text{limite atual})}$.
    #### 2. Matriz de Tiers de Risco e Consequência Comercial (A Tradução)
    A nota final do Scorecard é mapeada em faixas rígidas que definem o **Tier de Risco Corporativo** do cliente e determinam o seu fator multiplicador ($k$):

    * **Tier A — Risco Baixo (Score $\ge$ 75) $\rightarrow k = 1.2$:** Clientes excelentes e de alta fidelidade. O sistema libera um prêmio de +20% sobre a necessidade volumétrica bruta para capturar fatia de mercado.
    * **Tier B — Risco Moderado (Score 55 a 74) $\rightarrow k = 1.0$:** Perfil operacional padrão e saudável. O sistema adota neutralidade, alocando o limite exato correspondente ao giro de estoque financiado.
    * **Tier C — Risco Elevado (Score 40 a 54) $\rightarrow k = 0.5$:** Contas em observação ou sob estresse financeiro moderado. Como barreira defensiva, o sistema corta o limite calculado pela metade.
    * **Tier D — Risco Crítico (Score $<$ 40) $\rightarrow k = 0.0$:** Clientes com restritivos graves ou histórico inadimplente severo. O crédito comercial a prazo é zerado e a conta migra para o regime à vista.

    #### 3. Gatilhos de Governança (Reclassificação por Assimetria de Informações)
    Para blindar o patrimônio da distribuidora contra dados falsos ou falta de histórico, o MVP possui travas automáticas que sobrepõem o cálculo do scorecard e reclassificam o cliente imediatamente:
    * **Inconsistência Estrutural (Caso C08):** Se o analista identificar indícios de balanços inflados ou dados que não batem com o porte, o sistema anula a nota quantitativa e joga o cliente direto para o **Tier C ($k=0.5$)**, reduzindo a exposição e retendo o teto até auditoria de campo.
    * **Tratamento de Cold Start (Caso C05):** Clientes novos com relacionamento $\le$ 3 meses e histórico nulo não possuem dados para rodar o scorecard. O sistema força o enquadramento no **Tier C com $k=0.0$**, mantendo o limite a prazo zerado até a apresentação de colaterais líquidos ou maturação da conta.
    """)

# Quebra de espaço e separação de painel
st.markdown("<br><br><br>", unsafe_allow_html=True)
st.markdown("---")


st.header("MVP de Análise de Crédito — Simulador Prático")
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
    st.metric(label="Limite Máximo Recomendado (Alocação Segura)", value=formatar_brl(resultado['limite_concedido']))
    
    st.markdown("##### Diretriz Operacional de Cobrança e Gestão de Conta")
    st.info(resultado['acao_comercial'])
