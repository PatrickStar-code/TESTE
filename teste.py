from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from dotenv import load_dotenv
from selenium.webdriver.common.keys import Keys
import json
import time
import os
from fuzzywuzzy import fuzz

# ======== CONFIGURAÇÕES ========
load_dotenv()

USER = os.getenv("LOGIN", "")
PASSWORD = os.getenv("PASSWORD", "")

URL = "https://juizdefora-mg.vivver.com/login"

JSON_PATH = "teams_output.json"
WAIT_TIME = 10

input_file = Path(JSON_PATH)
markdown_text = input_file.read_text(encoding="utf-8") if input_file.exists() else ""

matrix_medico_erro = []
area_atual = None
medicos_adicionar = []
medicos_deletar = []

# ======== FUNÇÕES AUXILIARES ========

def carregar_dados_times(caminho):
    """Retorna sempre uma lista de times."""
    try:
        with open(caminho, "r", encoding="utf-8") as teamfile:
            leitor = json.load(teamfile)
            if isinstance(leitor, dict) and "teams" in leitor:
                dados = leitor["teams"] or []
            elif isinstance(leitor, list):
                dados = leitor
            else:
                # caso venha um dict com estrutura inesperada
                dados = []
    except FileNotFoundError:
        print(f"[ERRO] Arquivo JSON não encontrado: {caminho}")
        dados = []
    except json.JSONDecodeError as e:
        print(f"[ERRO] Erro ao ler o arquivo JSON: {e}")
        dados = []
    return dados


def esperar_e_clicar(espera, by, seletor, timeout=None):
    """Espera o elemento aparecer e clica (retorna elemento ou None)."""
    try:
        elem = WebDriverWait(espera._driver, timeout or espera._timeout).until(EC.element_to_be_clickable((by, seletor)))
        elem.click()
        return elem
    except TimeoutException:
        print(f"[ERRO] Tempo excedido ao procurar/clicar {seletor}")
        return None
    except Exception as e:
        print(f"[ERRO] Exceção ao clicar {seletor}: {e}")
        return None


def login(driver, espera):
    driver.get(URL)

    campo_conta = espera.until(EC.presence_of_element_located((By.ID, "conta")))
    if not campo_conta.get_attribute("value"):
        campo_conta.send_keys(USER)

    campo_senha = espera.until(EC.presence_of_element_located((By.NAME, "password")))
    campo_senha.send_keys(PASSWORD)

    esperar_e_clicar(espera, By.CLASS_NAME, "btn_entrar")

    try:
        popup = espera.until(EC.visibility_of_element_located((By.CLASS_NAME, "window_close")))
        popup.click()
    except TimeoutException:
        print("[INFO] Nenhuma janela de boas-vindas encontrada.")


def abrir_times(driver, espera, action):
    """Abre a área de times (encapsula abrir_formulario)."""
    abrir_formulario(driver=driver, espera=espera, action=action, shortcut_id="shortcut_esf_area_profissional")


def abrir_formulario(driver, espera, action, shortcut_id):
    """Abre o formulário fazendo duplo clique no atalho."""
    print("➡️ Esperando o shortcut...")
    shortcut = espera.until(EC.element_to_be_clickable((By.ID, shortcut_id)))
    print("✅ Shortcut encontrado")
    action.double_click(shortcut).perform()
    print("✅ Duplo clique executado")


# Função auxiliar para reduzir repetição de inserir município/segmento/unidade/area
def preencher_filtros_padrao(espera, action, unidade, area):
    """Preenche os filtros comuns: município, segmento, unidade e área."""
    try:
        inserir(espera=espera, action=action,
                id_campo="s2id_esf_area_profissional_id_municipio",
                campo_id="lookup_key_esf_area_profissional_id_municipio",
                valor="JUIZ DE FORA")
        inserir(espera=espera, action=action,
                id_campo="s2id_esf_area_profissional_id_segmento",
                campo_id="lookup_key_esf_area_profissional_id_segmento",
                valor="URBANO")
        inserir(espera=espera, action=action,
                id_campo="s2id_esf_area_profissional_id_unidade",
                campo_id="lookup_key_esf_area_profissional_id_unidade",
                valor=unidade)
        inserir(espera=espera, action=action,
                id_campo="s2id_esf_area_profissional_id_area",
                campo_id="lookup_key_esf_area_profissional_id_area",
                valor=area,
                controle=True)
    except Exception as e:
        print(f"[ERRO] preencher_filtros_padrao: {e}")


def pesquisar_unidade_por_area(driver, espera, action, dados, iframe_id):
    """Troca para o iframe e processa todas as equipes (times)."""
    # troca para iframe
    try:
        print("➡️ Trocando para o iFrame")
        iframe_elem = espera.until(EC.visibility_of_element_located((By.ID, iframe_id)))
        driver.switch_to.frame(iframe_elem)
        print("✅ Troca de frame bem sucedida")
    except TimeoutException:
        print("[ERRO] IFrame não encontrado")
        return
    except Exception as e:
        print(f"[ERRO] Erro ao trocar para iframe: {e}")
        return

    # garantir que dados é lista
    if isinstance(dados, dict):
        times = dados.get("teams", [])
    else:
        times = dados

    if not isinstance(times, list):
        print("[ERRO] Estrutura de dados de times inválida")
        return

    for i, team in enumerate(times, start=1):
        temp_team = team
        print(f"\n=== Processando equipe {i}/{len(times)} -> Unidade: {team.get('unid')} - Área: {team.get('area')} ===")
        # preenche filtros
        preencher_filtros_padrao(espera=espera, action=action, unidade=team.get("unid", ""), area=team.get("area", ""))

        time.sleep(1)
        print("-> Esperando botão pesquisar")
        btn_search = espera.until(EC.visibility_of_element_located((By.ID, "esf_area_profissional_search")))
        action.move_to_element(btn_search).click().perform()
        print("-> Botão pesquisar clicado")
        time.sleep(1)

        # Seleciona 100 linhas
        try:
            select_element = espera.until(EC.visibility_of_element_located((By.NAME, "esf_area_profissional_datatable_length")))
            select = Select(select_element)
            select.select_by_value("100")
        except Exception as e:
            print(f"[AVISO] Não foi possível ajustar o select de linhas: {e}")

        verificar_medico(driver=driver, espera=espera, action=action, dados=team.get("members", []), temp_team=temp_team)

    # volta para default content (caso o código externo precise)
    driver.switch_to.default_content()


def inserir(espera, action, id_campo, valor, campo_id, controle=False):

    try:
        print(f"➡️ Esperando o campo '{campo_id}' ser clicável")
        campo_id_element = espera.until(EC.element_to_be_clickable((By.ID, campo_id)))
        # limpar campo
        campo_id_element.clear()
        time.sleep(1)  # mantido

        print(f"➡️ Esperando o campo '{id_campo}' ser visível")
        campo = espera.until(EC.visibility_of_element_located((By.ID, id_campo)))
        action.move_to_element(campo).click().perform()
        # digita o valor
        campo_input = campo
        try:
            # alguns select2 esperam que se envie o texto no input interno
            campo_input.send_keys(valor)
        except Exception:
            # fallback: usar ActionChains para enviar
            action.send_keys(valor).perform()

        time.sleep(1)  # mantido para estabilidade do Select2
        print("Valor enviado (aguardando dropdown se aplicável)...")

        if controle:
            # se houver select2-drop, esperar e procurar opções
            try:
                espera.until(EC.visibility_of_element_located((By.ID, "select2-drop")))
                opcoes = espera.until(EC.presence_of_all_elements_located((
                    By.CSS_SELECTOR,
                    "#select2-drop ul.select2-results li.select2-result-selectable"
                )))

                clicou = False
                for opcao in opcoes:
                    try:
                        texto_op = opcao.text.strip()
                        if valor.lower() in texto_op.lower():
                            opcao.click()
                            clicou = True
                            print(f"✅ Clicado em: {texto_op}")
                            break
                    except StaleElementReferenceException:
                        continue

                if not clicou:
                    # tenta verificar se o campo foi preenchido automaticamente
                    try:
                        texto = campo.find_element(By.CSS_SELECTOR, ".select2-chosen").text.strip()
                        if texto == valor:
                            print("✅ O valor foi preenchido automaticamente (sem abrir o dropdown).")
                        else:
                            print(f"❌ Opção '{valor}' não encontrada na lista.")
                    except Exception:
                        print(f"❌ Opção '{valor}' não encontrada e não foi possível validar estado do campo.")
            except TimeoutException:
                # dropdown não apareceu
                try:
                    texto_atual = campo.find_element(By.CSS_SELECTOR, ".select2-chosen").text.strip()
                    if texto_atual == valor:
                        print("✅ O valor foi preenchido automaticamente (sem abrir o dropdown).")
                    else:
                        print(f"⚠️ O dropdown não apareceu e o valor ainda não é '{valor}'.")
                except Exception:
                    print("⚠️ Não foi possível validar o conteúdo do campo após tentativa de seleção.")
        else:
            print(f"✅ Inserção simples: '{valor}' enviada (controle=False).")

        print("✅ Inserção concluída")
        time.sleep(1)  
    except Exception as e:
        print(f"[ERRO] Não foi possível inserir o campo {id_campo} devido: {e}")


def verificar_medico(driver, espera, action, dados, temp_team):
    """
    Checa médicos listados na tabela e sincroniza com os membros (dados).
    """
    try:
        table = espera.until(EC.visibility_of_element_located((By.ID, "esf_area_profissional_datatable")))
    except TimeoutException:
        print("[ERRO] Tabela de profissionais não encontrada.")
        return

    try:
        tbody = table.find_element(By.TAG_NAME, "tbody")
        linhas = tbody.find_elements(By.TAG_NAME, "tr")
    except Exception as e:
        print(f"[ERRO] Falha ao obter linhas da tabela: {e}")
        linhas = []

    valores = []


    for linha in linhas:
        try:
            colunas = linha.find_elements(By.TAG_NAME, "td")
            # se a tabela informar "Não foram encontrados resultados"
            if len(colunas) == 1 and "Não foram encontrados resultados" in colunas[0].text:
                print("Equipe sem medicos")
                break
            # checamos se existe a coluna 9; caso contrário, procuramos pela coluna que mais faz sentido
            valores.append(colunas[9].text)
         
        except StaleElementReferenceException:
            continue
        except Exception as e:
            print(f"[AVISO] Erro ao ler linha da tabela: {e}")
            continue

    if len(valores) == 0:
        # se não encontrou ninguém cadastrado, adiciona todos do cnes
        for cnes in dados:
            adicionar_medico_equipe(driver=driver, espera=espera, action=action, pessoa=cnes.get("name"))
    else:
      

        # verificar quem precisa ser adicionado
        for cnes in dados:
            nome = cnes.get("name", "")
            encontrado = any(fuzz.ratio(nome.lower(), pessoa.lower()) > 80 for pessoa in valores)
            if encontrado:
                print(f"O médico '{nome}' está cadastrado corretamente")
            else:
                print(f"O médico '{nome}' não está na equipe — adicionando...")
                medicos_adicionar.append(nome)
                # adicionar_medico_equipe(driver=driver, espera=espera, action=action, pessoa=nome)

          # verificar quem saiu
        for pessoa in valores:
            encontrado = any(fuzz.ratio(pessoa, cnes.get("name", "")) >= 80 for cnes in dados)
            if not encontrado:
                print(f"O médico '{pessoa}' não está mais no CNES — deletando...")
                medicos_deletar.append(pessoa)
                # deletar_medico_equipe(espera=espera, medico=pessoa, actions=action, temp_team=temp_team)

    # Sai da tabela (botão cancelar)
    try:
        cancel = espera.until(EC.presence_of_element_located((By.ID, "esf_area_profissional_cancel")))
        action.move_to_element(cancel).click().perform()
    except Exception:
        pass


def adicionar_medico_equipe(driver, espera, action, pessoa):
    """Adiciona um médico à equipe (mantendo sleeps)."""
    try:
        print("-> Tentando cancelar (se estiver em modo edição)...")
        btn_cancel = espera.until(EC.visibility_of_element_located((By.ID, "esf_area_profissional_cancel")))
        action.move_to_element(btn_cancel).click().perform()
        print("-> Cancel Bem Sucedido")
    except Exception:
        pass

    time.sleep(1)

    try:
        print("-> Esperando o botão inserir")
        btn_inserir = espera.until(EC.visibility_of_element_located((By.ID, "esf_area_profissional_insert")))
        action.move_to_element(btn_inserir).click().perform()
        print("-> Botão inserir clicado")
    except Exception as e:
        print(f"[ERRO] Botão inserir não encontrado: {e}")
        matrix_medico_erro.append(pessoa or "UNKNOWN")
        return

    time.sleep(1)

    try:
        print("-> Inserindo dados do medico")
        inserir(espera=espera, action=action,
                id_campo="s2id_esf_area_profissional_id_profissional",
                campo_id="lookup_key_esf_area_profissional_id_profissional",
                valor=pessoa)
        print("-> Dado Inserido")
    except Exception as e:
        print(f"[ERRO] Falha ao inserir profissional: {e}")
        matrix_medico_erro.append(pessoa or "UNKNOWN")
        # tenta cancelar e seguir
        try:
            btn_cancel = espera.until(EC.presence_of_element_located((By.ID, "esf_area_profissional_cancel")))
            action.move_to_element(btn_cancel).click().perform()
        except Exception:
            pass
        return

    time.sleep(1)
    # espera pelo select2 mask invisível (mantendo sleep)
    try:
        espera.until(EC.invisibility_of_element_located((By.ID, "select2-drop-mask")))
    except Exception:
        pass

    print("-> Esperando botão salvar")
    try:
        btn_salvar = espera.until(EC.visibility_of_element_located((By.ID, "esf_area_profissional_save")))
        action.move_to_element(btn_salvar).click().perform()
        print("-> Botão salvar clicado")
    except Exception as e:
        print(f"[ERRO] Botão salvar não encontrado: {e}")
        matrix_medico_erro.append(pessoa or "UNKNOWN")
        return

    time.sleep(1)

    # Verifica se existe erro visível no topo (ex.: nav.fwk-navbar-danger)
    try:
        erro = driver.find_element(By.CSS_SELECTOR, "nav.fwk-navbar-danger")
        if erro.is_displayed():
            print(f"[ERRO] Erro ao salvar médico {pessoa}")
            matrix_medico_erro.append(pessoa or "UNKNOWN")
    except NoSuchElementException:
        # tudo ok
        pass
    except Exception as e:
        print(f"[AVISO] Ao verificar mensagem de erro: {e}")


def deletar_medico_equipe(espera, medico, actions, temp_team):
    """Deleta um médico da equipe e refaz a pesquisa (mantendo sleeps)."""
    try:
        td = espera.until(EC.visibility_of_element_located((By.XPATH, f"//table[@id='esf_area_profissional_datatable']//td[normalize-space(text())='{medico}']")))
        actions.double_click(td).perform()
        time.sleep(1)

        btn_excluir = espera.until(EC.visibility_of_element_located((By.ID, "esf_area_profissional_delete")))
        actions.move_to_element(btn_excluir).click().perform()
        time.sleep(1)

        btn_confirmar_exclusao = espera.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-footer .btn.btn-primary.btn-lg")))
        actions.move_to_element(btn_confirmar_exclusao).click().perform()
        time.sleep(1)

        # Após exclusão, re-pesquisar para atualizar lista
        try:
            preencher_filtros_padrao(espera=espera, action=actions, unidade=temp_team.get("unid", ""), area=temp_team.get("area", ""))
            btn_search = espera.until(EC.visibility_of_element_located((By.ID, "esf_area_profissional_search")))
            actions.move_to_element(btn_search).click().perform()
            time.sleep(1)
        except Exception as e:
            print(f"[AVISO] Não foi possível re-pesquisar após exclusão: {e}")

    except Exception as e:
        print(f"[ERRO] Falha ao deletar o medico '{medico}': {e}")


def main():
    dados = carregar_dados_times(JSON_PATH)
    if not dados:
        print("Nenhum dado carregado no JSON.")
        return

    driver = webdriver.Edge()
    espera = WebDriverWait(driver, WAIT_TIME)
    # armazenamos driver e timeout em espera (hack para usar o helper 'esperar_e_clicar')
    espera._driver = driver
    espera._timeout = WAIT_TIME
    action = ActionChains(driver)

    try:
        login(driver, espera)
        abrir_times(driver, espera, action)
        pesquisar_unidade_por_area(driver, espera, action, dados, "iframe_esf_area_profissional")
    except Exception as e:
        print(f"[ERRO] Ocorreu um erro no fluxo principal: {e}")
    finally:
        print("\n=== Relatório de médicos com erro ===")
        print(matrix_medico_erro)
        print("Fechando navegador...")
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
