from datetime import datetime, timedelta
from pythoncom import CoInitialize
from pywinauto import Application
from subprocess import Popen
from threading import Thread
from pandas import DataFrame
from platform import system
from random import randint
from pathlib import Path
import pygetwindow as gw
from time import sleep
import win32com.client
import psutil
from models.exceptions import ElementNotFound

class SapGui:
    def __init__(self, sid: str, user: str, pwd: str, mandante: str, root_sap_dir: str='C:\Program Files (x86)\SAP\FrontEnd\SAPGUI'):
        """
        sid: identificador do sistema, cada ambiente tem seu próprio SID. Normalmente são: PRD (produção) / DEV (desenvolvimento) / QAS (qualidade).
        usuario: usuário que a automação utilizará para realizar login.
        senha: senha que a automação utilizará para realizar login.
        diretorio_instalacao: diretório onde o sapshcut.exe se encontra, onde foi realizado a instalação do SAP.
        """
        self.sid = sid
        self.user = user
        self.__pwd = pwd
        self.language = 'PT'
        self.mandante = mandante
        self.root_sap_dir = Path(root_sap_dir)
        self.new_pwd = None
        self.logged = False
        self.info: GuiSessionInfo = self.session.Info

    def __enter__(self):
        self.start_sap()
        self.thread_conexao = Thread(target=self.verify_sap_connection,daemon=True)
        self.thread_conexao.start()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if self.logged:
            self.quit()
        
    def start_sap(self):
        """
        Starts the SAP application and establishes a session.

        This method attempts to launch the SAP application on a Windows OS and 
        establish a session by logging in with the provided credentials. It handles 
        multiple login attempts and manages password changes if required. The method 
        sets the `logado` attribute to `True` upon successful login.

        Raises:
            Exception: If the SAP application fails to start after multiple attempts 
            or if the SAP Application object cannot be obtained.
            ValueError: If the login attempt fails due to incorrect credentials.
        """
        if system() == 'Windows':
            tries = 0
            while tries <=5:
                try:
                    self.program = Popen(args=f'{self.root_sap_dir}/sapshcut.exe -system={self.sid} -client={self.mandante} -user={self.user} -pw={self.__pwd} -language={self.language}')
                    sleep(1)
                    self.SapGuiAuto = win32com.client.GetObject('SAPGUI',CoInitialize())
                    if self.SapGuiAuto:
                        break
                except Exception as e:
                    if tries >= 5:
                        raise Exception(f'Failed to get control of SAP: {e}.')
                    tries += 1

                    sleep(3)

            # Get the SAP Application object
            self.application = self.SapGuiAuto.GetScriptingEngine()
            if not self.application:
                raise Exception("Failed to get SAP Application object.")

            sleep(2)
            self.connection = self.application.Children(0)
            self.session: GuiSession = self.connection.Children(0)

            # Se aparecer a janela de x tentativas com a senha incorreta
            if self.find_by_id("wnd[1]/usr/txtMESSTXT1"):
                self.press_button("wnd[1]/tbar[0]/btn[0]")

            if self.get_user_logged() is None:
                if self.get_status_text() == 'O nome ou a senha não está correto (repetir o logon)':
                    raise ValueError('Failed to login with the provided credentials.')
                
                if self.find_by_id("wnd[1]/usr/radMULTI_LOGON_OPT1"):
                    self.find_by_id("wnd[1]/usr/radMULTI_LOGON_OPT1").select()
                    self.press_button("wnd[1]/tbar[0]/btn[0]")
            
            if self.find_by_id("wnd[1]/usr/lblRSYST-NCODE_TEXT"):
                # Se aparecer a tela de troca de senha, resetar a senha
                _current_date = datetime.now()
                _random = randint(0,100)
                _date = _current_date + timedelta(days=_random)
                self.new_pwd = _date.strftime("%B@%Y%H%M%f")

                self.set_text("wnd[1]/usr/pwdRSYST-NCODE", self.new_pwd)
                self.set_text("wnd[1]/usr/pwdRSYST-NCOD2", self.new_pwd)
                self.press_button("wnd[1]/tbar[0]/btn[0]")

                if self.find_by_id("wnd[1]/usr/txtMESSTXT1"):
                    self.press_button("wnd[1]/tbar[0]/btn[0]")

            self.logged = True
            self.maximize_window()
        else:
            raise Exception('This library only supports Windows OS')
        
    def get_user_logged(self):
        
        """
        Returns the user currently logged in.
        """
        return None if self.session.Info.User == '' else self.session.Info.User
    
    def login(self):
        self.find_by_id("wnd[0]").maximize()
        self.find_by_id("wnd[0]/usr/txtRSYST-BNAME").set_text(self.user)
        self.find_by_id("wnd[0]/usr/pwdRSYST-BCODE").set_text(self.__pwd)
        self.find_by_id("wnd[0]").sendVKey(0)

        if self.session.Info.User == '':
            if self.find_by_id("wnd[0]/sbar/pane[0]").text == 'O nome ou a senha não está correto (repetir o logon)':
                raise ValueError('Failed to login with the provided credentials.')
            
            self.find_by_id("wnd[1]/usr/radMULTI_LOGON_OPT1").select()
            self.find_by_id("wnd[1]/tbar[0]/btn[0]").press()

    def logoff(self):
        self.find_by_id("wnd[0]").maximize()
        self.find_by_id("wnd[0]/tbar[0]/okcd").set_text("/nend")
        self.find_by_id("wnd[0]").sendVKey(0)
        self.find_by_id("wnd[1]/usr/btnSPOP-OPTION1").press()

    def quit(self):
        self.program.terminate()

        for proc in psutil.process_iter(['pid', 'name']):
            if 'saplogon' in proc.info['name'].lower():
                proc.kill()

        self.logged = False

    def open_transaction(self,transacao: str):
        self.session.startTransaction(transacao)
    
    def get_window_size(self):
        try:
            height = self.find_by_id("wnd[0]").Height
            width = self.find_by_id("wnd[0]").Width
            return width, height
        except Exception:
            raise Exception('Não foi possível obter o tamanho da janela do SAP')
        
    def verify_sap_connection(self):
        while self.logged:
            sleep(10)
            #Se a janela com o titulo 'SAP GUI for Windows 800' está aparecendo, significa que o SAP caiu. Então a execução deve ser interrompida.
            windows = gw.getWindowsWithTitle('SAP GUI for Windows 800')
            if windows:
                # Fechar a janela
                for window in windows:
                    try:
                        app = Application().connect(handle=window._hWnd)
                        app_window = app.window(handle=window._hWnd)
                        app_window.close()
                        self.logged = False
                    except Exception as e:
                        raise Exception(f'Não foi possível fechar a janela do SAP: {e}')
        else:
            return
        
    def find_by_id(self, element_id: str, raise_error: bool = True):
        """
        Returns a instance of the GuiElement class supplied with the specified ID.
        """
        element = self.session.FindById(element_id)

        if element is None and raise_error:
            raise ElementNotFound(f"The element with ID '{element_id}' was not found.")
        
        element_type = element.Type
        
        match element_type.lower():
            case "guibutton":
                return GuiButton(element)
            case "guitextfield":
                return GuiTextField(element)
            case "guicombo":
                return GuiComboBox(element)
            case "guicheckbox":
                return GuiCheckBox(element)
            case "guictextfield":
                return GuiCTextField(element)
            case "guitab":
                return GuiTab(element)
            case "guigridview":
                return GuiGridView(element)
            case "guishell":
                return GuiShell(element)
            case "guitree":
                return GuiTree(element)
            case "guiframewindow":
                return GuiFrameWindow(element)
            case _:
                raise TypeError(f"Element type '{element_type}' is not supported.")
                

class GuiButton:
    def __init__(self, element):
        self.element = element
    
    def press(self):
        """Pressiona o botão."""
        self.element.Press()

class GuiTextField:
    def __init__(self, element):
        self.element = element
    
    def set_text(self, text):
        """Define um valor de texto no campo."""
        self.element.Text = text
    
    def get_text(self):
        """Obtém o valor de texto do campo."""
        return self.element.Text

class GuiComboBox:
    def __init__(self, element):
        self.element = element
    
    def select_entry(self, entry):
        """Seleciona uma entrada no ComboBox."""
        self.element.Key = entry

class GuiCheckBox:
    def __init__(self, element):
        self.element = element
    
    def select(self, value=True):
        """Marca ou desmarca a caixa de seleção."""
        self.element.Selected = value

class GuiCTextField:
    def __init__(self, element):
        self.element = element
    
    def set_text(self, text):
        """Define um valor de texto no campo com formato controlado."""
        self.element.Text = text
    
    def get_text(self):
        """Obtém o valor de texto do campo com formato controlado."""
        return self.element.Text

class GuiTab:
    def __init__(self, element):
        self.element = element
    
    def select(self):
        """Seleciona a aba."""
        self.element.Select()

class GuiGridView:
    def __init__(self, element):
        self.element = element
    
    def select_row(self, row):
        """Seleciona uma linha específica na GridView."""
        self.element.Rows.SelectedRow = row
    
    def get_cell_value(self, row, column):
        """Obtém o valor de uma célula específica."""
        return self.element.GetCellValue(row, column)
    
    def set_cell_value(self, row, column, value):
        """Define o valor de uma célula específica."""
        self.element.SetCellValue(row, column, value)

class GuiShell:
    def __init__(self, element):
        self.element = element

    @property
    def rows_count(self):
        return self.element.RowCount
    
    @property
    def columns_order(self):
        return self.element.ColumnOrder
    
    def send_command(self, command):
        """Sends a command to the shell."""
        self.element.SendCommand(command)
    
    def get_cell_value(self, row, column):
        """Returns the value of a specific cell."""
        return self.element.GetCellValue(row, column)

    def read_shell_table(self) -> DataFrame:
        """Return a shell table as a pandas DataFrame."""
        columns = self.columns_order
        rows_count = self.rows_count
        data = [
                {column: self.get_cell_value(i, column) for column in columns}
                for i in range(rows_count)
                ]
        
        return DataFrame(data)

class GuiTree:
    def __init__(self, element):
        self.element = element
    
    def expand_node(self):
        """Expande um nó na árvore."""
        self.element.Expand()
    
    def collapse_node(self):
        """Colapsa um nó na árvore."""
        self.element.Collapse()
    
    def select_node(self, node_key):
        """Seleciona um nó específico na árvore."""
        self.element.SelectNode(node_key)

class GuiStatusbar:
    def __init__(self, element):
        self.element = element
    
    def get_text(self):
        """Obtém o texto da barra de status."""
        return self.element.Text

class GuiFrameWindow:
    def __init__(self, element):
        self.element = element
    
    def maximize(self):
        """Maximiza a janela."""
        self.element.Maximize()
    
    def minimize(self):
        """Minimiza a janela."""
        self.element.Iconify()
    
    def restore(self):
        """Restaura a janela ao seu tamanho original."""
        self.element.Restore()

    def close_session(self):
        """Fecha a sessão atual."""
        self.session.EndSession()

class GuiSession:
    def __init__(self, element):
        self.element = element
    
    def send_vkey(self, vkey):
        """Envia uma tecla de função para a sessão atual."""
        self.element.SendVKey(vkey)
    
    def end_session(self):
        """Fecha a sessão atual."""
        self.element.EndSession()
    
    def start_transaction(self, transaction):
        """Inicia uma transação."""
        self.element.StartTransaction(transaction)
    
    def close_transaction(self):
        """Fecha a transação atual."""
        self.element.EndTransaction()

class GuiSessionInfo:
    def __init__(self, element):
        self.element = element
    
    def get_user(self):
        """Obtém o usuário logado na sessão."""
        return self.element.Info.User
    
    def get_client(self):
        """Obtém o cliente da sessão."""
        return self.element.Info.Client
    
    def get_transaction(self):
        """Obtém a transação atual da sessão."""
        return self.element.Info.Transaction
    
    def get_program(self):
        """Obtém o programa atual da sessão."""
        return self.element.Info.Program
    
    def get_system(self):
        """Obtém o sistema da sessão."""
        return self.element.Info.System
    
class GuiApplication:
    def __init__(self, element):
        self.element = element
    
    @property
    def name(self):
        """Obtém o nome da aplicação."""
        return self.element.Name
    
    @property
    def version(self):
        """Obtém a versão da aplicação."""
        return self.element.Version
    
    def open_connection(self, connection_string):
        """Abre uma conexão com a string fornecida."""
        return self.element.OpenConnection(connection_string)