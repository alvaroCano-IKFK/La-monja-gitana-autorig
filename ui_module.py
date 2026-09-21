import maya.cmds as cmds
from PySide2 import QtGui, QtCore, QtWidgets
from maya.OpenMayaUI import MQtUtil
from shiboken2 import wrapInstance

import module_specs
import guides_module
import guides_io_module
import mirror_module
import build_module
import eyes_module

#Recarrega en calent: a Maya els moduls es queden a la cache i si no es
#recarreguen, els canvis als specs no arriben mai a la finestra.
try:
    from importlib import reload
except ImportError:
    pass

reload(module_specs)


def maya_main_window():
    """
    Widget de la finestra principal de Maya.

    Va aqui i no com a valor per defecte d un argument. Un valor per defecte
    s avalua UNA sola vegada, quan Python llegeix el fitxer: si el modul
    s importa abans que Maya hagi acabat de construir la seva interficie,
    MQtUtil.mainWindow() torna None i aquell None es queda enganxat per a
    sempre, fins i tot despres de recarregar. Cridant-ho aqui es resol cada
    cop que s obre la finestra.
    """
    pointer = MQtUtil.mainWindow()

    if pointer is None:
        return None

    return wrapInstance(int(pointer), QtWidgets.QWidget)


class Window(QtWidgets.QDialog):

    #Les opcions de cada modul NO viuen aqui: viuen a module_specs.py, que es
    #el mateix fitxer que llegeix el build. Aixi la finestra i la construccio
    #no poden dir coses diferents.

    #Amplades de la finestra. L amplada final es la base mes el que afegeixi
    #cada panell lateral que estigui obert: els dos panells (afegir moduls i
    #Tools) son independents i es poden tenir oberts alhora.
    WIDTH_PANEL_CLOSED = 450          #base: columna principal + pestanya Tools
    WIDTH_PANEL_OPEN = 630            #base + panell d afegir moduls (compatibilitat)
    WIDTH_MODULES_PANEL = WIDTH_PANEL_OPEN - WIDTH_PANEL_CLOSED
    WIDTH_TOOLS_PANEL = 290

    #Alcada amb la que s obre la finestra. Es un minim: si el contingut en
    #demana mes, mana el contingut. I mai passa del 85% de la pantalla.
    INITIAL_HEIGHT = 720
    BUTTON_MIN_HEIGHT = 32

    COLOR_BACKGROUND = "rgb(237, 236, 232)"      
    COLOR_PANEL_BG = "rgb(247, 246, 243)"      
    COLOR_BORDER = "rgb(205, 203, 198)"         
    COLOR_HEADER_BG = "rgb(222, 220, 215)"      
    COLOR_HEADER_BG_HOVER = "rgb(230, 228, 223)"
    COLOR_HEADER_TEXT = "rgb(75, 72, 68)"        
    COLOR_PRESSED_BG = "rgb(210, 208, 202)"
    COLOR_SELECTED_BG = "rgb(224, 221, 216)"
    COLOR_ACCENT = "rgb(114, 22, 26)"           
    COLOR_ACCENT_HOVER = "rgb(150, 34, 38)"      

    def __init__(self, parent=None):
        """
        Finestra de l autorig de La Monja Gitana.

        Sempre penja de la finestra principal de Maya: aixi no es perd darrere
        del viewport, es tanca sola quan es tanca Maya i no apareix com una
        aplicacio separada a la barra de tasques.
        """
        super(Window, self).__init__(parent or maya_main_window())

        self.setWindowTitle("Autorig Bíped")

        # Qt.Window en lloc de Qt.Dialog: un QDialog normal no te el boto de
        # minimitzar a la barra de titol. Amb Qt.Window si, i seguim sent
        # filla de Maya perque el parent ja s ha passat al super().
        #
        # WindowStaysOnTopHint es manté perque la finestra estigui sempre
        # visible per sobre del viewport mentre es treballa.
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowSystemMenuHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowStaysOnTopHint
        )

        #Nomes amplada minima. L alcada minima la calcula el layout a partir
        #del contingut: abans hi havia un setMinimumSize(300, 360) explicit que
        #anul.lava aquest calcul, i Qt deixava aixafar els botons fins que el
        #text desapareixia. La mida inicial es posa al final del __init__, quan
        #el layout ja existeix i es pot saber quant ocupa.
        self.setMinimumWidth(320)

        #Fons general de la finestra
        self.setStyleSheet("QDialog {{ background-color: {bg}; }}".format(bg=self.COLOR_BACKGROUND))

        #Cada fila del arbre: quin tipus de modul es i quin combo de costat li toca
        self.module_rows = []

        self.character = guides_module.CharacterGuides()
        self.mirror_guides = mirror_module.Mirror()
        self.builder = build_module.BuildRig()

        self.populate()
        self.create_layouts()
        self.create_connections()

        self._set_initial_size()

    def general_style(self, button):
        """
        Aplica un StyleSheet general, discret i professional, a tots els botons
        """
        #Alcada minima fixa: encara que la finestra es faci petita, el boto no
        #es pot aixafar per sota d aixo i el text sempre es llegeix.
        button.setMinimumHeight(self.BUTTON_MIN_HEIGHT)

        button.setStyleSheet("""
            QPushButton {{
                background-color: {panel_bg};
                color: {accent};
                font-family: 'Palatino Linotype', 'Georgia', serif;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 1px;
                border: 1px solid {border};
                border-radius: 3px;
                padding-top: 7px;
                padding-bottom: 7px;
            }}

            QPushButton:hover {{
                background-color: {panel_bg};
                border: 1px solid {accent};
                color: {accent_hover};
            }}

            QPushButton:pressed {{
                background-color: {pressed_bg};
            }}
        """.format(
            panel_bg=self.COLOR_PANEL_BG,
            accent=self.COLOR_ACCENT,
            accent_hover=self.COLOR_ACCENT_HOVER,
            border=self.COLOR_BORDER,
            pressed_bg=self.COLOR_PRESSED_BG,
        ))

    def tab_style(self, button):
        """
        Estil de les pestanyetes laterals que despleguen panells. El comparteixen
        la d afegir moduls i la de Tools, perque es vegin com la mateixa peca.
        """
        button.setStyleSheet("""
            QPushButton {{
                background-color: {header_bg};
                color: {accent};
                font-family: 'Palatino Linotype', serif;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid {border};
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {header_bg_hover};
                border: 1px solid {accent};
            }}
            QPushButton:pressed {{
                background-color: {pressed_bg};
            }}
        """.format(
            header_bg=self.COLOR_HEADER_BG,
            header_bg_hover=self.COLOR_HEADER_BG_HOVER,
            accent=self.COLOR_ACCENT,
            border=self.COLOR_BORDER,
            pressed_bg=self.COLOR_PRESSED_BG,
        ))

    def scrollbar_css(self):
        """
        Barra de desplacament fina i del color de la finestra. La de Maya per
        defecte es gris fosc i queda com un pegat enmig del paper beix.
        """
        return """
            QScrollBar:vertical {{
                background: {panel_bg};
                width: 8px;
                margin: 0px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {header_bg};
                border: 1px solid {border};
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {accent};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """.format(panel_bg=self.COLOR_PANEL_BG,
                   header_bg=self.COLOR_HEADER_BG,
                   border=self.COLOR_BORDER,
                   accent=self.COLOR_ACCENT)

    def field_style(self, widget):
        """Mateix aire que els botons, per als camps de text i els combos."""
        widget.setStyleSheet("""
            QLineEdit, QComboBox {{
                background-color: {panel_bg};
                color: {accent};
                font-family: 'Georgia', serif;
                font-size: 12px;
                border: 1px solid {border};
                border-radius: 3px;
                padding: 4px 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {panel_bg};
                color: {accent};
                selection-background-color: {selected_bg};
            }}
        """.format(panel_bg=self.COLOR_PANEL_BG,
                   accent=self.COLOR_ACCENT,
                   border=self.COLOR_BORDER,
                   selected_bg=self.COLOR_SELECTED_BG))

    def hint_label(self, text):
        """Text petit d ajuda, per no deixar els botons sense context."""
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("""
            QLabel {{
                font-family: 'Georgia', serif;
                font-size: 11px;
                color: {header_text};
                background-color: transparent;
            }}
        """.format(header_text=self.COLOR_HEADER_TEXT))
        return label

    def collapsible(self, title):
        """
        Crea un widget desplegable amb un boto i el que hi ha al seu interior
        """
        collapsible_widget = QtWidgets.QWidget()

        collapsible_layout = QtWidgets.QVBoxLayout(collapsible_widget)
        collapsible_layout.setContentsMargins(0, 0, 0, 0)
        collapsible_layout.setSpacing(4)

        btn_title = QtWidgets.QPushButton("▼ " + title)

        btn_title.setStyleSheet("""
            QPushButton {{
                background-color: {header_bg};
                color: {header_text};
                font-family: 'Palatino Linotype', 'Georgia', serif;
                font-size: 14px;
                font-weight: 600;
                text-align: left;
                padding-left: 12px;
                padding-top: 6px;
                padding-bottom: 6px;
                border: 1px solid {border};
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {header_bg_hover};
                color: {accent};
                border: 1px solid {accent};
            }}
            QPushButton:pressed {{
                background-color: {pressed_bg};
            }}
        """.format(
            header_bg=self.COLOR_HEADER_BG,
            header_bg_hover=self.COLOR_HEADER_BG_HOVER,
            header_text=self.COLOR_HEADER_TEXT,
            border=self.COLOR_BORDER,
            accent=self.COLOR_ACCENT,
            pressed_bg=self.COLOR_PRESSED_BG,
        ))

        contingut_widget = QtWidgets.QWidget()
        contingut_layout = QtWidgets.QVBoxLayout(contingut_widget)
        contingut_layout.setContentsMargins(5, 5, 5, 5)
        contingut_layout.setSpacing(6)

        collapsible_layout.addWidget(btn_title)
        collapsible_layout.addWidget(contingut_widget)

        def collapsible_logic():
            ara_visible = contingut_widget.isVisible()
            contingut_widget.setVisible(not ara_visible)
            fletxa = "🞂" if ara_visible else "▼"
            btn_title.setText("{} {}".format(fletxa, title))

        btn_title.clicked.connect(collapsible_logic)

        return collapsible_widget, contingut_layout

    def populate(self):
        #Titol amb tipografia cal·ligrafica en granate, sobre el mateix fons
        #de la finestra (com el logo de La Monja Gitana)
        self.title_label = QtWidgets.QLabel("༻La Monja Gitana༺")
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.title_label.setStyleSheet("""
            QLabel {{
                font-family: 'Bickham Script Pro', 'Edwardian Script ITC', 'Segoe Script',
                             'Brush Script MT', 'Palatino Linotype', 'Georgia', serif;
                font-style: bold;
                font-size: 28px;
                font-weight: 600;
                letter-spacing: 1px;
                color: {accent};
                background-color: transparent;
                padding: 6px;
            }}
        """.format(accent=self.COLOR_ACCENT))

        #Boto de minimitzar propi. La barra de titol ja en te un (pel flag
        #WindowMinimizeButtonHint), pero amb WindowStaysOnTopHint la barra
        #queda amagada en alguns gestors de finestres, aixi que aquest sempre
        #esta a ma.
        self.minimize_btn = QtWidgets.QPushButton("—")
        self.minimize_btn.setFixedSize(26, 22)
        self.minimize_btn.setToolTip("Minimitzar la finestra")
        self.general_style(self.minimize_btn)

        self.subtitle_label = QtWidgets.QLabel("A U T O R I G")
        self.subtitle_label.setAlignment(QtCore.Qt.AlignCenter)
        self.subtitle_label.setStyleSheet("""
            QLabel {{
                font-family: 'Georgia', serif;
                font-size: 11px;
                letter-spacing: 4px;
                color: {header_text};
                background-color: transparent;
                padding-bottom: 6px;
            }}
        """.format(header_text=self.COLOR_HEADER_TEXT))

        #-------------------------------------------------
        # 1. Data management
        #-------------------------------------------------
        self.data_title = self.collapsible("1. Data management")

        #El boto de guies ja no viu aqui: s ha mogut a "2. Modules", perque ara
        #crea nomes les guies dels moduls de l arbre.
        #
        #QUADRUPED TEMPLATE es queda comentat, no esborrat: no estava connectat
        #a res, i es el lloc on anira la plantilla del quadrupede.
        # self.guides_btn02 = QtWidgets.QPushButton("QUADRUPED TEMPLATE")
        # self.general_style(self.guides_btn02)

        self.export_btn = QtWidgets.QPushButton("EXPORT GUIDES")
        self.general_style(self.export_btn)

        self.import_btn = QtWidgets.QPushButton("IMPORT GUIDES")
        self.general_style(self.import_btn)

        self.mirror_btn = QtWidgets.QPushButton("MIRROR")
        self.general_style(self.mirror_btn)

        #-------------------------------------------------
        # 2. Moduls
        #-------------------------------------------------
        self.modules_title = self.collapsible("2. Modules")

        #Arbre de moduls: cada modul (Arm, Spine, Leg, Finger...) es un item arrel
        #i les seves opcions (IK, FK, Twist, Soft...) son els seus fills
        self.modules_tree = QtWidgets.QTreeWidget()
        self.modules_tree.setHeaderHidden(True)
        self.modules_tree.setColumnCount(1)
        self.modules_tree.setIndentation(14)
        self.modules_tree.setMinimumHeight(150)
        self.modules_tree.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.modules_tree.setStyleSheet("""
            QTreeWidget {{
                background-color: {panel_bg};
                color: {accent};
                font-family: 'Georgia', serif;
                font-size: 12px;
                border: 1px solid {border};
                border-radius: 3px;
                padding: 3px;
            }}
            QTreeWidget::item {{
                padding: 3px;
            }}
            QTreeWidget::item:selected {{
                background-color: {selected_bg};
                color: {accent};
            }}
        """.format(
            panel_bg=self.COLOR_PANEL_BG,
            accent=self.COLOR_ACCENT,
            border=self.COLOR_BORDER,
            selected_bg=self.COLOR_SELECTED_BG,
        ) + self.scrollbar_css())

        #Boto de guies, petit, sota l arbre. Crea nomes les guies dels moduls
        #que hi ha a l arbre (mira create_guides).
        self.guides_btn = QtWidgets.QPushButton("GUIDES")
        self.general_style(self.guides_btn)
        self.guides_btn.setMinimumHeight(24)
        self.guides_btn.setFixedWidth(90)
        self.guides_btn.setToolTip("Crea les guies dels moduls de l arbre. "
                                   "Les que ja existeixen no es toquen.")
        self.guides_btn.setStyleSheet(self.guides_btn.styleSheet().replace(
            "font-size: 13px;", "font-size: 11px;").replace(
            "padding-top: 7px;", "padding-top: 3px;").replace(
            "padding-bottom: 7px;", "padding-bottom: 3px;"))

        #Petita pestanyeta lateral per desplegar/plegar el panell d afegir moduls
        self.add_panel_tab_btn = QtWidgets.QPushButton("▸")
        self.add_panel_tab_btn.setFixedWidth(22)
        self.add_panel_tab_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.tab_style(self.add_panel_tab_btn)

        #Panell lateral amb els moduls que es poden afegir, amagat per defecte
        self.add_module_panel = QtWidgets.QWidget()
        self.add_module_panel.setVisible(False)
        panel_layout = QtWidgets.QVBoxLayout(self.add_module_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(5)

        panel_title = QtWidgets.QLabel("Afegeix un modul")
        panel_title.setAlignment(QtCore.Qt.AlignCenter)
        panel_title.setStyleSheet("""
            QLabel {{
                font-family: 'Georgia', serif;
                font-size: 12px;
                color: {accent};
                padding: 3px;
            }}
        """.format(accent=self.COLOR_ACCENT))
        panel_layout.addWidget(panel_title)

        #Els botons van dins d un scroll vertical. Amb deu moduls (i els que
        #vinguin), deu botons de 32 px empenyien la finestra cap avall: el
        #panell forcava l alcada de tota la seccio de moduls. Ara el panell fa
        #l alcada de l arbre i la resta es desplaca.
        buttons_widget = QtWidgets.QWidget()
        buttons_widget.setObjectName("moduleButtons")
        buttons_layout = QtWidgets.QVBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 4, 0)   #lloc per la barra
        buttons_layout.setSpacing(5)

        #Crea un boto per cada tipus de modul declarat als specs
        self.module_type_buttons = []
        for module_type in module_specs.module_types():
            btn = QtWidgets.QPushButton(module_specs.module_label(module_type).upper())
            self.general_style(btn)
            buttons_layout.addWidget(btn)
            self.module_type_buttons.append((btn, module_type))

        buttons_layout.addStretch()

        self.module_buttons_scroll = QtWidgets.QScrollArea()
        self.module_buttons_scroll.setWidget(buttons_widget)
        self.module_buttons_scroll.setWidgetResizable(True)
        self.module_buttons_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.module_buttons_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.module_buttons_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        #Alcada minima petita: si no, el scroll demanaria l alcada de tots els
        #botons i tornariem a tenir el mateix problema.
        self.module_buttons_scroll.setMinimumHeight(60)
        self.module_buttons_scroll.setStyleSheet(
            "QScrollArea, #moduleButtons { background: transparent; }"
            + self.scrollbar_css())
        panel_layout.addWidget(self.module_buttons_scroll, 1)

        #-------------------------------------------------
        # 3. Eye loop curves
        #
        # Els ulls son l unic modul que necessita un pas a ma ABANS del build:
        # seleccionar l edge loop de la parpella i crear la corba. D aquesta
        # corba surt tant la linia de la parpella com els joints de loop, aixi
        # que sense ella el modul d ulls no te d on partir.
        #-------------------------------------------------
        #-------------------------------------------------
        # TOOLS (panell lateral dret)
        #
        # Eines que no son passos del flux principal: es fan servir un cop, a
        # ma, abans del build. Van en un panell lateral que ocupa tota
        # l alcada de la finestra, amagat per defecte, amb la mateixa
        # mecanica que el panell d afegir moduls.
        #-------------------------------------------------
        self.tools_tab_btn = QtWidgets.QPushButton()
        self.tools_tab_btn.setFixedWidth(22)
        self.tools_tab_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.tools_tab_btn.setToolTip("Tools")
        self.tab_style(self.tools_tab_btn)
        self._set_tools_tab_text(opened=False)

        self.tools_panel = QtWidgets.QWidget()
        self.tools_panel.setFixedWidth(self.WIDTH_TOOLS_PANEL - 30)
        self.tools_panel.setVisible(False)

        self.tools_title = QtWidgets.QLabel("Tools")
        self.tools_title.setAlignment(QtCore.Qt.AlignCenter)
        self.tools_title.setStyleSheet("""
            QLabel {{
                font-family: 'Palatino Linotype', 'Georgia', serif;
                font-size: 15px;
                font-weight: 600;
                color: {accent};
                padding: 4px;
            }}
        """.format(accent=self.COLOR_ACCENT))

        #Cada eina es un desplegable dins del panell, com les seccions de la
        #columna principal. Aixi afegir-ne una de nova es crear un altre
        #collapsible i posar-lo a sota.
        self.eyes_title = self.collapsible("Eye loop curves")

        self.eye_rig_name_field = QtWidgets.QLineEdit("Character")
        self.field_style(self.eye_rig_name_field)

        self.eye_side_combo = QtWidgets.QComboBox()
        self.eye_side_combo.addItems(["L", "R"])
        self.field_style(self.eye_side_combo)

        self.eye_upper_btn = QtWidgets.QPushButton("UPPER LOOP CURVE")
        self.general_style(self.eye_upper_btn)

        self.eye_lower_btn = QtWidgets.QPushButton("LOWER LOOP CURVE")
        self.general_style(self.eye_lower_btn)

        # ---- DESACTIVAT DE MOMENT ------------------------------------
        # Inner ref, check i diagnose. El codi es queda aqui perque funciona;
        # nomes esta comentat perque a la finestra fa nosa. Per tornar-ho a
        # activar cal descomentar QUATRE blocs, tots marcats amb
        # "DESACTIVAT DE MOMENT":
        #   1. aquests widgets (populate)
        #   2. el seu layout (create_layouts)
        #   3. els metodes (_get_inner_reference i companyia)
        #   4. les connexions (create_connections)
        #
        # I al metode build_loop_curve, tornar a posar
        # inner_reference=self._get_inner_reference() on ara hi ha None.
        #
        # self.eye_inner_ref_field = QtWidgets.QLineEdit("")
        # self.eye_inner_ref_field.setPlaceholderText("opcional: node del centre de la cara")
        # self.field_style(self.eye_inner_ref_field)
        #
        # self.eye_inner_ref_btn = QtWidgets.QPushButton("<< SEL")
        # self.general_style(self.eye_inner_ref_btn)
        # self.eye_inner_ref_btn.setFixedWidth(70)
        #
        # self.eye_check_btn = QtWidgets.QPushButton("CHECK LOOP CURVES")
        # self.general_style(self.eye_check_btn)
        #
        # self.eye_diag_upper_btn = QtWidgets.QPushButton("DIAGNOSE UPPER")
        # self.general_style(self.eye_diag_upper_btn)
        #
        # self.eye_diag_lower_btn = QtWidgets.QPushButton("DIAGNOSE LOWER")
        # self.general_style(self.eye_diag_lower_btn)
        # --------------------------------------------------------------

        #-------------------------------------------------
        # 3. Build rig
        #-------------------------------------------------
        self.build_title = self.collapsible("3. Build rig")

        self.build_btn = QtWidgets.QPushButton("BUILD")
        self.general_style(self.build_btn)

    def create_layouts(self):
        #Arrel horitzontal: a l esquerra la columna de sempre, a la dreta la
        #pestanya de Tools i el seu panell, tots dos d alcada completa.
        root_layout = QtWidgets.QHBoxLayout(self)
        root_layout.setSpacing(6)
        root_layout.setContentsMargins(10, 10, 10, 10)

        main_column = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_column)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(0, 0, 0, 0)

        root_layout.addWidget(main_column, 1)
        root_layout.addWidget(self.tools_tab_btn)
        root_layout.addWidget(self.tools_panel)

        #El titol va centrat a la finestra sencera, aixi que el boto de
        #minimitzar es posa en una fila propia a sobre, alineat a la dreta.
        #Si es posessin els dos a la mateixa fila, el boto desplacaria el titol
        #cap a l esquerra i deixaria de estar centrat.
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addStretch()
        header_layout.addWidget(self.minimize_btn)
        main_layout.addLayout(header_layout)

        main_layout.addWidget(self.title_label)
        main_layout.addWidget(self.subtitle_label)

        main_layout.addWidget(self.data_title[0])
        main_layout.addWidget(self.modules_title[0])
        main_layout.addWidget(self.build_title[0])

        main_layout.addStretch()

        # self.data_title[1].addWidget(self.guides_btn02)

        imp_exp_layout = QtWidgets.QHBoxLayout()
        imp_exp_layout.addWidget(self.export_btn)
        imp_exp_layout.addWidget(self.import_btn)
        self.data_title[1].addLayout(imp_exp_layout)

        self.data_title[1].addWidget(self.mirror_btn)
        modules_row_layout = QtWidgets.QHBoxLayout()
        modules_row_layout.setSpacing(5)
        modules_row_layout.addWidget(self.modules_tree)
        modules_row_layout.addWidget(self.add_panel_tab_btn)
        modules_row_layout.addWidget(self.add_module_panel)
        self.modules_title[1].addLayout(modules_row_layout)

        guides_row_layout = QtWidgets.QHBoxLayout()
        guides_row_layout.setContentsMargins(0, 0, 0, 0)
        guides_row_layout.addWidget(self.guides_btn)
        guides_row_layout.addStretch()
        self.modules_title[1].addLayout(guides_row_layout)

        # ---- TOOLS ----
        tools_layout = QtWidgets.QVBoxLayout(self.tools_panel)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)
        tools_layout.addWidget(self.tools_title)
        tools_layout.addWidget(self.eyes_title[0])
        tools_layout.addStretch()

        # ---- Tools > Eye loop curves ----
        eye_naming_layout = QtWidgets.QHBoxLayout()
        eye_naming_layout.addWidget(self.hint_label("Rig name"))
        eye_naming_layout.addWidget(self.eye_rig_name_field)
        eye_naming_layout.addWidget(self.hint_label("Side"))
        eye_naming_layout.addWidget(self.eye_side_combo)
        self.eyes_title[1].addLayout(eye_naming_layout)

        self.eyes_title[1].addWidget(
            self.hint_label("Selecciona l edge loop de la vora de la parpella i crea la corba:"))
        self.eyes_title[1].addWidget(self.eye_upper_btn)
        self.eyes_title[1].addWidget(self.eye_lower_btn)

        # ---- DESACTIVAT DE MOMENT ------------------------------------
        # eye_ref_layout = QtWidgets.QHBoxLayout()
        # eye_ref_layout.addWidget(self.hint_label("Inner ref"))
        # eye_ref_layout.addWidget(self.eye_inner_ref_field)
        # eye_ref_layout.addWidget(self.eye_inner_ref_btn)
        # self.eyes_title[1].addLayout(eye_ref_layout)
        #
        # self.eyes_title[1].addWidget(self.eye_check_btn)
        #
        # eye_diag_layout = QtWidgets.QHBoxLayout()
        # eye_diag_layout.addWidget(self.eye_diag_upper_btn)
        # eye_diag_layout.addWidget(self.eye_diag_lower_btn)
        # self.eyes_title[1].addLayout(eye_diag_layout)
        # --------------------------------------------------------------

        # ---- 3. Build rig ----
        self.build_title[1].addWidget(self.build_btn)

    def create_joints(self, joint_name):
        cmds.select(clear=True)
        cmds.joint(name=joint_name)

    def _set_initial_size(self):
        """
        Mida amb la que s obre la finestra.

        Parteix de INITIAL_HEIGHT, pero si el contingut necessita mes (fonts
        grans, escalat de pantalla de Windows al 125 o 150%) mana el sizeHint
        del layout. I es limita al 85% de l alcada util de la pantalla, perque
        en un portatil no quedi la meitat de la finestra fora.
        """
        hint = self.sizeHint()

        width = max(self.WIDTH_PANEL_CLOSED, hint.width())
        height = max(self.INITIAL_HEIGHT, hint.height())

        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry().height()
            height = min(height, int(available * 0.85))

        self.resize(width, height)

    def _update_width(self):
        """
        Recalcula l amplada de la finestra segons quins panells estan oberts.

        Abans cada panell posava una amplada fixa. Amb dos panells independents
        aixo ja no val: obrir Tools amb el panell de moduls obert el faria
        encongir. Ara es suma el que ocupi cada un.

        Es fa servir isHidden() i no isVisible(): isVisible() tambe torna False
        si la finestra sencera esta minimitzada, i llavors l amplada calculada
        seria erronia.
        """
        width = self.WIDTH_PANEL_CLOSED

        if not self.add_module_panel.isHidden():
            width += self.WIDTH_MODULES_PANEL

        if not self.tools_panel.isHidden():
            width += self.WIDTH_TOOLS_PANEL

        self.resize(width, self.height())

    def toggle_add_panel(self):
        """Desplega o plega el panell lateral d afegir moduls."""
        panell_obert = not self.add_module_panel.isHidden()
        self.add_module_panel.setVisible(not panell_obert)
        self.add_panel_tab_btn.setText("▸" if panell_obert else "◂")

        self._update_width()

    def _set_tools_tab_text(self, opened):
        """
        Text de la pestanya de Tools: fletxa i la paraula en vertical, perque
        la pestanya fa 22 px d ample i s ha de saber que es sense obrir-la.
        """
        arrow = "◂" if opened else "▸"
        self.tools_tab_btn.setText(arrow + "\n\n" + "\n".join("TOOLS"))

    def toggle_tools_panel(self):
        """Desplega o plega el panell lateral de Tools."""
        panell_obert = not self.tools_panel.isHidden()
        self.tools_panel.setVisible(not panell_obert)
        self._set_tools_tab_text(opened=not panell_obert)

        self._update_width()

    def create_module_item_widget(self, module_type):
        """
        Crea el widget visual d un item de modul: el nom a l esquerra, el
        selector de costat al mig i una creueta per treure l a la dreta.

        El selector de costat es el que faltava: a la finestra vella afegies
        ARM i no hi havia manera de saber si era l esquerre, el dret o els dos.

        Args:
            module_type (str): La clau del modul als specs (arm, spine, leg...)

        Returns:
            tuple: (widget del item, boto de la creueta, combo de costat o None)
        """
        item_widget = QtWidgets.QWidget()
        item_layout = QtWidgets.QHBoxLayout(item_widget)
        item_layout.setContentsMargins(4, 0, 4, 0)
        item_layout.setSpacing(4)

        label = QtWidgets.QLabel(module_specs.module_label(module_type).upper())
        label.setStyleSheet("""
            color: {accent};
            font-family: 'Georgia', serif;
            font-weight: bold;
            font-size: 12px;
            background: transparent;
        """.format(accent=self.COLOR_ACCENT))

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setStyleSheet("""
            QPushButton {{
                background-color: transparent;
                color: {accent};
                border: none;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {accent_hover};
            }}
        """.format(accent=self.COLOR_ACCENT, accent_hover=self.COLOR_ACCENT_HOVER))

        #Selector de costat. Els moduls de centre (spine) no en tenen.
        side_combo = None
        sides = module_specs.module_sides(module_type)

        if sides != ["C"]:
            side_combo = QtWidgets.QComboBox()
            side_combo.addItems(sides + [" + ".join(sides)])
            side_combo.setCurrentIndex(len(sides))   #per defecte, els dos costats
            side_combo.setFixedWidth(64)
            side_combo.setStyleSheet("""
                QComboBox {{
                    background-color: {panel_bg};
                    color: {accent};
                    font-family: 'Georgia', serif;
                    font-size: 11px;
                    border: 1px solid {border};
                    border-radius: 3px;
                    padding: 1px 4px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {panel_bg};
                    color: {accent};
                    selection-background-color: {selected_bg};
                }}
            """.format(panel_bg=self.COLOR_PANEL_BG,
                       accent=self.COLOR_ACCENT,
                       border=self.COLOR_BORDER,
                       selected_bg=self.COLOR_SELECTED_BG))

        item_layout.addWidget(label)
        item_layout.addStretch()
        if side_combo:
            item_layout.addWidget(side_combo)
        item_layout.addWidget(close_btn)

        return item_widget, close_btn, side_combo

    def add_module(self, module_type):
        """
        Afegeix un modul a l arbre amb les seves features com a fills.

        Les features que van sempre (IK, FK, switch, pole vector) surten
        marcades i bloquejades: l usuari veu que hi son pero no les pot
        treure. Les que encara no estan implementades surten en gris.

        Args:
            module_type (str): La clau del modul als specs (arm, spine, leg...)
        """
        module_item = QtWidgets.QTreeWidgetItem(self.modules_tree)
        module_item.setText(0, "")
        module_item.setData(0, QtCore.Qt.UserRole, module_type)

        item_widget, close_btn, side_combo = self.create_module_item_widget(module_type)
        close_btn.clicked.connect(
            lambda checked=False, itm=module_item: self.remove_module_item(itm))
        self.modules_tree.setItemWidget(module_item, 0, item_widget)

        self.module_rows.append({
            "item": module_item,
            "type": module_type,
            "side_combo": side_combo,
        })

        defaults = module_specs.default_feature_keys(module_type)

        #Features fixes: marcades i no editables
        for feature in module_specs.always_features(module_type):
            child = QtWidgets.QTreeWidgetItem(module_item)
            child.setText(0, feature.label)
            child.setData(0, QtCore.Qt.UserRole, feature.key)
            child.setFlags(QtCore.Qt.ItemIsEnabled)
            child.setCheckState(0, QtCore.Qt.Checked)
            child.setForeground(0, QtGui.QBrush(QtGui.QColor(150, 148, 143)))
            child.setToolTip(0, "Aquesta feature va sempre en un {}.".format(
                module_specs.module_label(module_type)))

        #Features opcionals
        for feature in module_specs.optional_features(module_type):
            child = QtWidgets.QTreeWidgetItem(module_item)
            child.setText(0, feature.label)
            child.setData(0, QtCore.Qt.UserRole, feature.key)

            if not feature.implemented:
                child.setFlags(QtCore.Qt.NoItemFlags)
                child.setCheckState(0, QtCore.Qt.Unchecked)
                child.setToolTip(0, "Encara no implementada.")
                continue

            child.setFlags(child.flags() | QtCore.Qt.ItemIsUserCheckable)
            child.setCheckState(
                0,
                QtCore.Qt.Checked if feature.key in defaults else QtCore.Qt.Unchecked)

            if feature.requires:
                needs = ", ".join(
                    module_specs.find_feature(module_type, key).label
                    for key in feature.requires)
                child.setToolTip(0, "Necessita: {}".format(needs))

        module_item.setExpanded(True)
        print("Modul afegit: {}".format(module_specs.module_label(module_type)))

    def remove_module_item(self, item):
        """
        Treu un modul (i les seves features) de l arbre a partir de la creueta.

        Args:
            item (QTreeWidgetItem): L item del modul a treure
        """
        index = self.modules_tree.indexOfTopLevelItem(item)
        if index == -1:
            return

        module_type = item.data(0, QtCore.Qt.UserRole)
        self.modules_tree.takeTopLevelItem(index)
        self.module_rows = [row for row in self.module_rows if row["item"] is not item]
        print("Modul tret: {}".format(module_type))

    # ------------------------------------------------------------------
    # RECEPTA
    # ------------------------------------------------------------------
    def collect_recipe(self):
        """
        Llegeix l arbre i torna la recepta: una llista de diccionaris
        {"type": "arm", "side": "L", "features": {...}}.

        Aquesta llista es l unic que viatja de la finestra al build. La
        finestra no construeix res, nomes descriu que s ha de construir.

        Returns:
            list: la recepta en brut, sense normalitzar
        """
        recipe = []

        for row in self.module_rows:
            module_item = row["item"]
            module_type = row["type"]

            #Features marcades (les fixes tambe surten marcades, i resolve les
            #tornaria a afegir igualment)
            features = set()
            for i in range(module_item.childCount()):
                child = module_item.child(i)
                if child.checkState(0) == QtCore.Qt.Checked:
                    features.add(child.data(0, QtCore.Qt.UserRole))

            #Un combo a "L + R" es converteix en dues entrades de la recepta
            combo = row["side_combo"]
            if combo is None:
                sides = ["C"]
            else:
                sides = [side.strip() for side in combo.currentText().split("+")]

            for side in sides:
                recipe.append({"type": module_type,
                               "side": side,
                               "features": set(features)})

        return recipe

    # ------------------------------------------------------------------
    # EXPORT / IMPORT
    # ------------------------------------------------------------------
    def export_guides(self):
        """
        Guarda les guies I la configuracio de moduls al mateix JSON.

        Sense la recepta, exportar nomes guardaria les posicions: obriries Maya
        l endema, importaries, i l arbre de moduls estaria buit. Amb ella, el
        fitxer es el rig sencer.
        """
        return guides_io_module.export_guides(recipe=self.collect_recipe())

    def import_guides(self):
        """
        Reconstrueix les guies i, si el fitxer en porta, torna a muntar l arbre
        de moduls tal com estava quan es va exportar.
        """
        result = guides_io_module.import_guides(return_data=True)

        if not result or not result.get("root"):
            return None

        recipe = result.get("recipe")
        if recipe:
            self.apply_recipe(recipe)

        return result.get("root")

    def apply_recipe(self, recipe):
        """
        Buida l arbre i el torna a omplir a partir d una recepta.

        Les entrades del mateix tipus amb les mateixes features s ajunten en una
        sola fila amb el combo a "L + R", que es com les hauria afegit l usuari.
        Si un costat te features diferents de l altre, es queden en dues files
        separades: ajuntar-les perdria informacio.
        """
        self.modules_tree.clear()
        self.module_rows = []

        grouped = []          # [((tipus, frozenset features), [costats]), ...]
        index_by_key = {}

        for entry in recipe:
            key = (entry["type"], frozenset(entry.get("features") or []))

            if key in index_by_key:
                grouped[index_by_key[key]][1].append(entry["side"])
            else:
                index_by_key[key] = len(grouped)
                grouped.append((key, [entry["side"]]))

        for (module_type, features), sides in grouped:
            if module_type not in module_specs.MODULE_SPECS:
                cmds.warning("[UI] El fitxer porta un modul desconegut "
                             "('{}'). S ignora.".format(module_type))
                continue

            self.add_module(module_type)
            row = self.module_rows[-1]

            self._apply_row_sides(row, sides)
            self._apply_row_features(row, features)

        print("[UI] Arbre de moduls restaurat: {} files.".format(
            len(self.module_rows)))

    def _apply_row_sides(self, row, sides):
        """Posa el combo de costat de la fila segons els costats de la recepta."""
        combo = row["side_combo"]

        if combo is None:      # moduls de centre (spine, jaw): no en tenen
            return

        # L ordre del combo es el dels specs, no el de la recepta: "L + R",
        # mai "R + L".
        ordered = [side for side in module_specs.module_sides(row["type"])
                   if side in sides]
        wanted = " + ".join(ordered)

        index = combo.findText(wanted)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            cmds.warning("[UI] No puc posar el costat '{}' al modul {}."
                         .format(wanted, row["type"]))

    def _apply_row_features(self, row, features):
        """Marca les features de la fila segons la recepta."""
        item = row["item"]

        for i in range(item.childCount()):
            child = item.child(i)

            # Les fixes i les no implementades no son marcables: es queden
            # com les ha deixat add_module.
            if not (child.flags() & QtCore.Qt.ItemIsUserCheckable):
                continue

            key = child.data(0, QtCore.Qt.UserRole)
            child.setCheckState(
                0,
                QtCore.Qt.Checked if key in features else QtCore.Qt.Unchecked)

    # ------------------------------------------------------------------
    # CORBES DE LOOP DELS ULLS
    # ------------------------------------------------------------------
    def _get_eye_naming(self):
        """
        Lado y nombre de rig que hay puestos en la ventana. Son solo para
        construir el nombre de la curva: la configuracion del build sigue
        viviendo en build_module, aqui no se guarda nada.
        """
        rig_name = self.eye_rig_name_field.text() or "Character"
        side = self.eye_side_combo.currentText() or "L"

        return side, rig_name.strip()

    # ---- DESACTIVAT DE MOMENT ----------------------------------------
    # def _get_inner_reference(self):
    #     """
    #     Nodo de referencia del centro de la cara, o None si el campo esta
    #     vacio o apunta a algo que ya no existe.
    #     """
    #     value = (self.eye_inner_ref_field.text() or "").strip()
    #
    #     if not value:
    #         return None
    #
    #     if not cmds.objExists(value):
    #         cmds.warning("[UI] '{}' no existe en la escena. Se ignora la "
    #                      "referencia y se usa la X mundial 0.".format(value))
    #         return None
    #
    #     return value
    #
    # def set_inner_reference_from_selection(self):
    #     """Mete en el campo el primer nodo seleccionado, para no escribirlo."""
    #     selection = cmds.ls(selection=True, long=False) or []
    #
    #     # Un componente no vale como referencia: hace falta un transform.
    #     selection = [item for item in selection if "." not in item]
    #     if not selection:
    #         cmds.warning("[UI] Selecciona un nodo del centro de la cara.")
    #         return None
    #
    #     self.eye_inner_ref_field.setText(selection[0])
    #
    #     return selection[0]
    # ------------------------------------------------------------------

    def build_loop_curve(self, upper=True):
        """
        Crea la curva de loop del parpado a partir del edge seleccionado, con
        el nombre de convencion para que el modulo la encuentre sola.
        """
        side, rig_name = self._get_eye_naming()

        # inner_reference=None mentre el camp esta desactivat. OJO: aixo NO es
        # cosmetic. Amb None, eyes_module decideix quin extrem del loop es la
        # comissura interna comparant contra la X de mon 0, cosa que nomes val
        # si el personatge esta centrat a l origen. Si algun dia una corba surt
        # girada del reves, torna a activar el camp Inner ref.
        return eyes_module.EyesModule.build_loop_curve_from_selection(
            side, rig_name, upper=upper,
            inner_reference=None
        )

    # ---- DESACTIVAT DE MOMENT ----------------------------------------
    # def report_loop_curves(self):
    #     """Imprime que curvas de loop hay y cuantos joints saldrian."""
    #     side, rig_name = self._get_eye_naming()
    #
    #     return eyes_module.EyesModule.report_loop_curves(side, rig_name)
    #
    # def diagnose_loop_curve(self, upper=True):
    #     """
    #     Imprime, CV a CV, donde cae sobre la linea del parpado y a que
    #     distancia. Necesita el rig ya construido: la linea no existe antes.
    #     """
    #     side, rig_name = self._get_eye_naming()
    #
    #     return eyes_module.EyesModule.diagnose_loop_curve(side, rig_name, upper=upper)
    # ------------------------------------------------------------------

    def create_guides(self):
        """
        Crea les guies NOMES dels moduls que hi ha a l arbre.

        Es pot cridar mes d un cop: si afegeixes un modul nou a l arbre i
        tornes a donar a GUIDES, nomes apareixen les guies d aquest modul. Les
        que ja hi eren no es toquen, aixi que no perds el que ja havies col.locat.
        """
        raw_recipe = self.collect_recipe()

        if not raw_recipe:
            cmds.warning("[Guides] L arbre de moduls esta buit. Afegeix algun "
                         "modul abans de crear les guies.")
            return None

        #Es normalitza per dos motius: afegeix el spine obligatori (el chest, el
        #hip i el coll en llegeixen les guies) i resol les features, que es
        #d on surt si la cama porta dits del peu o no.
        recipe, warnings = module_specs.normalize_recipe(raw_recipe)
        for text in warnings:
            cmds.warning("[Recepta] {}".format(text))

        return self.character.create_guides(recipe)

    def mirror_rig(self):
        """
        Espeja las guias del lado L al R.

        Se le pasa la recepta EN BRUT, sense normalitzar: si l arbre esta buit,
        collect_recipe() torna una llista buida i el modul entén que ha
        d espejar-ho tot. Si la normalitzessim, s hi afegiria l spine
        obligatori i el mirror es pensaria que hi ha configuracio quan no n hi
        ha.
        """
        self.mirror_guides.mirror(self.collect_recipe())

    def build_rig(self):
        if not self.module_rows:
            print("No hi ha cap modul afegit per construir el rig.")
            return

        recipe, warnings = module_specs.normalize_recipe(self.collect_recipe())

        for text in warnings:
            cmds.warning("[Recepta] {}".format(text))

        print("Construint rig amb:")
        print(module_specs.describe_recipe(recipe))

        self.builder.build(recipe)

    def create_connections(self):
        self.guides_btn.clicked.connect(self.create_guides)
        #self.guides_btn02.clicked.connect(lambda: self.character.create_guides())

        self.export_btn.clicked.connect(self.export_guides)
        self.import_btn.clicked.connect(self.import_guides)
        self.mirror_btn.clicked.connect(self.mirror_rig)

        #Connecta la pestanyeta lateral per desplegar/plegar el panell d afegir moduls
        self.add_panel_tab_btn.clicked.connect(self.toggle_add_panel)
        self.tools_tab_btn.clicked.connect(self.toggle_tools_panel)

        #Connecta cada boto del panell amb el tipus de modul que afegeix
        for btn, module_type in self.module_type_buttons:
            btn.clicked.connect(
                lambda checked=False, m=module_type: self.add_module(m))

        self.eye_upper_btn.clicked.connect(
            lambda: self.build_loop_curve(upper=True))
        self.eye_lower_btn.clicked.connect(
            lambda: self.build_loop_curve(upper=False))
        # ---- DESACTIVAT DE MOMENT ------------------------------------
        # self.eye_inner_ref_btn.clicked.connect(self.set_inner_reference_from_selection)
        # self.eye_check_btn.clicked.connect(self.report_loop_curves)
        # self.eye_diag_upper_btn.clicked.connect(
        #     lambda: self.diagnose_loop_curve(upper=True))
        # self.eye_diag_lower_btn.clicked.connect(
        #     lambda: self.diagnose_loop_curve(upper=False))
        # --------------------------------------------------------------

        self.minimize_btn.clicked.connect(self.showMinimized)

        self.build_btn.clicked.connect(self.build_rig)


if __name__ == "__main__":
    try:
        #window_instance.close()
        window_instance = None
    except:
        pass

    window_instance = Window()
    window_instance.show()