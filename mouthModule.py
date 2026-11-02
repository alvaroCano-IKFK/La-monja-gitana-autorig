import math

import maya.cmds as cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaAnim as oma

from groups_module import ControlsGroups

try:
    import controlsLibrary
except ImportError:
    controlsLibrary = None


class SimpleMouthModule(object):
    """
    Boca sin curvas, sin NURBS y sin nodos de geometria.

    Todo el sistema son joints, controles y parentConstraints con pesos. No hay
    motionPath, ni uvPin, ni closestPointOnSurface, ni composeMatrix, ni
    aimMatrix. Es a proposito: esta pensado como base minima sobre la que ir
    anadiendo capas y poder aislar que hace cada una.

    LA CADENA
    ---------
    Por cada mitad (upper y lower) y por cada lado hay cuatro posiciones, que
    salen de las guias:

        mid ---- in01 ---- in02 ---- comisura
                (levator   (pinch
                 depresor)

    Y se cuelgan asi:

        mid           parentConstraint 100% al control del jaw de su mitad
        in01          parentConstraint  mid 75% / comisura 25%
        in02          parentConstraint  mid 25% / comisura 75%
        comisura      parentConstraint  jawUpper / jawLower segun UpperLower

    Por que no puede flipar: ningun control saca su orientacion de la forma de
    una curva ni de una superficie. Un parentConstraint mezcla dos transforms
    que ya existen, y con interpType Shortest esa mezcla es un slerp, que es
    continuo por construccion.
    """

    # base_name -> peso del MID (la comisura se lleva 1 - peso)
    #
    #   01 = levator / depresor   -> mid 0.80 / comisura 0.20
    #   02 = upperPinch / lowerPinch -> mid 0.33 / comisura 0.66
    CHAIN_WEIGHTS = {
        "01": 0.8,
        "02": 0.33,
    }

    # Forma y tamano por defecto cuando una clave no esta en styles.
    DEFAULT_STYLE = "circleControl"
    DEFAULT_STYLE_SCALE = 1.0

    # Como se llama cada eslabon en cada mitad
    CHAIN_NAMES = {
        "Upper": {"01": "levator", "02": "upperPinch"},
        "Lower": {"01": "depresor", "02": "lowerPinch"},
    }

    def __init__(self, rig_name="Character", root_instance=None,
                 lip_mid="C_lip_mid", lip_end="L_lip_end",
                 lip_in01="L_lip_in01", lip_in02="L_lip_in02",
                 jaw_upper_ctrl=None, jaw_lower_ctrl=None,
                 sides=("L", "R"), control_size=0.6,
                 wrap_surfaces=("mouth_wrapUpper_NRB", "mouth_wrapLower_NRB"),
                 wrap_targets=None, wrap_surface=None):

        self.rig_name = rig_name
        self.root_instance = root_instance
        self.groups = ControlsGroups()

        # Guias. Solo existen en +X; el lado R se saca espejando la X.
        self.lip_mid = lip_mid
        self.lip_end = lip_end
        self.lip_in01 = lip_in01
        self.lip_in02 = lip_in02

        # Controles del jaw. Si no se pasan, se buscan por convencion.
        self.jaw_upper_ctrl = jaw_upper_ctrl or f"C_{rig_name}_jawUpper_CTRL"
        self.jaw_lower_ctrl = jaw_lower_ctrl or f"C_{rig_name}_jawLower_CTRL"

        self.sides = sides
        self.control_size = control_size

        # ==========================================================
        # FORMAS DE LOS CONTROLES
        # ----------------------------------------------------------
        # Igual que self.styles de limbs_module: la clave es el papel que
        # hace el control y el valor es el nombre del JSON de la libreria,
        # sin la extension. Para ver los que tienes:
        #
        #     import controlsLibrary
        #     controlsLibrary.report_library_sizes()
        #
        # Si un nombre no existe en la libreria, create_control_from_lib
        # avisa y cae a un circulo, asi que una clave mal escrita no rompe
        # el build pero se ve en el script editor.
        # "midUpper" y "midLower" van por separado: son dos controles
        # distintos, uno en cada labio, y antes los dos leian la misma clave
        # "mid" y salian iguales.
        self.styles = {
            "midUpper":   "mouthUpper",
            "midLower":   "mouthLower",
            "corner":     "L_lipCorner",
            "levator":    "mouthUpper",
            "depresor":   "mouthLower",
            "upperPinch": "mouthUpper",
            "lowerPinch": "mouthLower",
        }

        # Ajuste de tamano por control, multiplicando la escala global del
        # rig. Va aparte de styles porque una misma forma puede necesitar
        # tamanos distintos segun donde este: las comisuras suelen pedir algo
        # mas pequeno que el centro del labio.
        #
        # Lo que no este aqui usa DEFAULT_STYLE_SCALE.
        self.style_scales = {
            "corner": 0.8,
        }

        # ==========================================================
        # DESPLAZAMIENTO DE LOS CVs
        # ----------------------------------------------------------
        # Mueve la SHAPE, no el control. Los CVs se apartan del pivote pero el
        # transform se queda donde esta, con los canales a cero.
        #
        # Es lo que hay que hacer aqui: si movieras el control, moverias
        # tambien su pivote, y con el se irian el joint que lo sigue y los
        # constraints que lo usan de padre. Asi solo cambia donde ves el dibujo
        # y puedes separarlo del labio para poder pincharlo sin pelearte con la
        # malla.
        #
        # El labio de arriba sube y el de abajo baja. Las comisuras no llevan
        # entrada: se quedan sobre el borde, que es donde toca.
        #
        # Va en el espacio del CONTROL, no del mundo. Como los controles
        # heredan la orientacion de su guia, la Y del control sigue el angulo
        # del labio en vez de ir recta hacia arriba.
        self.style_cv_offsets = {
            "midUpper":   (0.0, 1.0, 0.0),
            "levator":    (0.0, 1.0, 0.0),
            "upperPinch": (0.0, 1.0, 0.0),

            "midLower":   (0.0, -1.0, 0.0),
            "depresor":   (0.0, -1.0, 0.0),
            "lowerPinch": (0.0, -1.0, 0.0),
        }

        # A True el desplazamiento se multiplica por la escala global del rig,
        # la misma que aplica controlsLibrary a las shapes. Asi un personaje
        # mas grande separa los controles proporcionalmente y no se le quedan
        # pegados al labio.
        self.scale_cv_offsets = True

        # Reparto de la comisura entre las dos mitades de la mandibula.
        # 0.5 = parentConstraint al 50% entre jawUpper y jawLower, que es lo
        # que hace que al abrir la boca la comisura se quede a medio camino en
        # vez de irse entera con el labio de abajo.
        self.corner_upper_lower = 0.5

        # A True añade un atributo 'UpperLower' animable en el control de la
        # comisura, conectado a los dos pesos con un reverse. Es una capa mas,
        # asi que por defecto va apagado: los pesos se quedan fijos al 50%.
        self.corner_upper_lower_attr = False

        self.controls = {}
        self.joints = {}
        self.module_group = None

        # Grupos que hay que enganchar al jaw. Se guardan porque el jaw puede
        # construirse DESPUES que la boca, y entonces attach_to_jaw() se llama
        # mas tarde (lo hace build_module desde _build_jaw).
        self.mid_groups = {}
        self.corner_groups = {}
        self.attached_to_jaw = False

        # ==========================================================
        # CASCADA
        # ----------------------------------------------------------
        # Una curva por labio, con un CV por control:
        #   comisuraR - pinchR - levatorR - mid - levatorL - pinchL - comisuraL
        # Cada control mueve SU CV, y los eslabones intermedios (levator,
        # depresor, pinch) siguen a la curva en posicion. Como la curva es de
        # grado 3, el punto de cada eslabon depende de los CVs vecinos: mover
        # un control empuja un poco a los de al lado.
        #
        # La ROTACION no cambia: sigue saliendo del parentConstraint entre el
        # mid y la comisura, que es lo que evita los flips. La curva solo
        # aporta DONDE, nunca COMO.
        #
        # use_cascade = False  -> exactamente el sistema anterior, solo
        #                         constraints.
        # cascade_amount       -> 0 = posicion solo de los constraints,
        #                         1 = posicion solo de la curva.
        # ==========================================================
        self.use_cascade = True
        self.cascade_amount = 1.0
        self.cascade_links = {}
        self.cascade_group = None

        # control -> nodo por el que se lee desde fuera (el propio control en
        # L, su _out_TRN en R). Ver _insert_mirror.
        self.output_nodes = {}



        # ==========================================================
        # PROXIMITY WRAP  (montaje de REFERENCE DRIVER)
        # ----------------------------------------------------------
        # Para que el caballo rebufe hay que deformar TODO el morro, no solo
        # el borde del labio. Con joints eso significa o pegarlos a
        # muchisimos vertices o meter mas joints, y las dos cosas se pintan
        # fatal.
        #
        # El montaje son DOS NURBS IGUALES y un deformer que mira la
        # diferencia entre ellas:
        #
        #     mouthWrapRef_NRB  (referencia)  se mueve como los joints
        #     mouthWrapDef_NRB  (deformacion) lo mismo + el rebufo
        #                   \             /
        #                    proximityWrap        -> malla de la cara
        #                   (solo pasa la RESTA)
        #
        # Esto es el "reference driver" del manual de Maya. Lo normal es que
        # el wrap compare la NURBS contra su forma original en bind pose; si
        # en vez de eso se le da otra version VIVA, lo que transmite es la
        # separacion entre las dos.
        #
        # La ventaja es que todo lo que hacen las dos a la vez SE CANCELA:
        # girar la cabeza, abrir la mandibula, caminar. La malla ya se mueve
        # por su propio skin y el wrap no lo duplica. Solo sobrevive lo que
        # le hagas a la Def y no a la Ref.
        #
        # Y como nacen identicas, la resta da cero: el sistema queda montado
        # pero inerte, y construir no cambia nada de lo que ya funciona.
        self.use_proximity_wrap = False

        # UNA NURBS POR LABIO. Al rebufar, el labio de arriba y el de abajo
        # hacen cosas distintas, y una sola superficie no puede deformarse de
        # dos maneras a la vez.
        #
        # Es una lista y no dos variables a proposito: cada superficie se
        # convierte en UN DRIVER del mismo proximityWrap, asi que anadir las
        # aletas manana es meter un nombre mas aqui.
        if isinstance(wrap_surfaces, str):
            wrap_surfaces = (wrap_surfaces,)
        self.wrap_surfaces = list(wrap_surfaces)
        # Compatibilidad con el parametro antiguo de una sola superficie.
        if wrap_surface:
            self.wrap_surfaces = [wrap_surface]
        # Mallas a deformar. Un nombre o una lista.
        if isinstance(wrap_targets, str):
            wrap_targets = [wrap_targets]
        self.wrap_targets = list(wrap_targets or [])

        # A True el modulo skinea las dos NURBS a los joints de la boca con
        # los mismos pesos, para que el sistema nazca vivo en vez de muerto.
        # Las deja IDENTICAS: la resta da cero y todavia no deforma nada. El
        # rebufo sale de repintar la Def mas abierta que la Ref, que es el
        # trabajo a mano que viene despues.
        self.wrap_auto_skin = True

        # MODO DEL WRAP. "Offset" en vez del "Surface" por defecto.
        #
        # Surface intenta mantener la posicion de cada vertice RELATIVA A LA
        # SUPERFICIE, reconstruyendo un marco de ejes (normal y tangentes) en
        # el punto mas cercano. Donde la superficie se dobla fuerte -- las
        # comisuras de la boca, justo donde se rompia -- ese punto salta de un
        # lado al otro del pliegue, el marco gira de golpe y los vertices
        # salen disparados: esas esquirlas.
        #
        # Offset es mas tonto y por eso mas robusto: desplaza cada vertice por
        # el MISMO VECTOR que se ha movido el driver cerca de el, sin
        # reconstruir ningun marco. Para transmitir un delta, que es
        # exactamente lo que hacemos, es lo que toca.
        # Offset solo TRASLADA: cada vertice recibe el vector que se
        # desplaza el punto mas cercano de la lamina, asi que si la
        # lamina se CURVA el vertice no se entera del giro, solo recibe
        # un empujon. Surface guarda el vertice en el marco local de la
        # superficie (posicion + normal + tangente) y entonces si gira
        # con ella, que es lo que hace falta para un rizo de labio.
        #
        # Antes estaba en Offset porque Surface sacaba astillas: el
        # marco de superficie se vuelve loco donde la lamina no esta
        # pegada a la malla. Con wrap_conform eso ya no pasa.
        self.wrap_mode = "Surface"

        # REFERENCE DRIVER (el truco del delta).
        #
        # A True, driverBindGeometry recibe una SEGUNDA lamina VIVA
        # skineada igual que la primera, y el wrap transmite solo la
        # RESTA entre las dos. Sirve para una cosa concreta: que la
        # malla no se lleve dos veces el movimiento que YA tiene por su
        # propio skin. Girar la cabeza mueve las dos laminas igual, la
        # resta da cero y el wrap no suma nada encima.
        #
        # A False se comporta como un wrap normal: la malla SIGUE a la
        # lamina, y punto. Es lo que hay que usar cuando la malla no
        # esta skineada, porque entonces no hay nada que cancelar y el
        # delta solo resta movimiento que nunca se sumo.
        #
        # Ademas es mas barato: con el delta hay que evaluar DOS
        # laminas skineadas y DOS cages por labio en cada frame. Sin
        # el, la de referencia se queda quieta y deja de recalcularse.
        self.wrap_use_reference_driver = False

        # Ajustes del deformer. maxDrivers a 1 porque solo hay un driver.
        self.wrap_max_drivers = 1
        self.wrap_falloff_scale = 1.4
        # smoothInfluences es UN PASE DE SUAVIZADO POR VERTICE: es con
        # diferencia lo mas caro del deformer. A 5 o mas se nota al arrastrar
        # un control; a 1 o 2 la calidad apenas cambia.
        self.wrap_smooth_influences = 3
        # Solo para drivers NURBS: muestras por span.
        self.wrap_span_samples = 2

        # DISTANCIA DE INFLUENCIA, en unidades de escena. driverFalloffEnd
        # viene de Maya a 1.0, o sea un radio de una unidad: en un personaje
        # de 24 unidades de alto no alcanza a ningun vertice y el deformer
        # parece no hacer nada aunque este bien conectado.
        #
        # None = se calcula como una fraccion del tamano de la NURBS, que
        # escala con el personaje.
        self.wrap_falloff_distance = None
        # Esa fraccion. El falloff es la distancia PERPENDICULAR a la que
        # llega la influencia, no el largo de la superficie, asi que tiene
        # que ser una parte pequena. Antes se usaba la mitad del lado mayor
        # y en una NURBS de 56 unidades salian 28: el wrap se comia medio
        # caballo y se arrastraba.
        self.wrap_falloff_ratio = 0.35

        # LA MESETA. driverFalloffStart es la distancia hasta la que el peso
        # vale 1 ENTERO; a partir de ahi empieza la rampa hacia 0.
        #
        # Esto estaba a 0 y era el fallo gordo: sin meseta, el peso cae
        # desde la propia superficie, asi que de verdad solo pesaban los
        # vertices que TOCAN la NURBS. En el caballo eso son cuatro
        # vertices de las comisuras (donde la lamina atraviesa la malla):
        # se los llevaba el wrap enteros -> pinchazos, y el resto del morro,
        # a una o dos unidades, con peso casi cero -> no se movia aunque
        # mandaras la NURBS a tomar viento.
        #
        # Se expresa como FRACCION del falloffEnd para que escale solo.
        # 0.5 = la mitad del alcance con peso 1 y la otra mitad de rampa.
        self.wrap_falloff_start_ratio = 0.5
        # Valor absoluto, si lo quieres a mano. None = se usa el ratio.
        self.wrap_falloff_start = None

        # PEGAR LA SUPERFICIE AL MORRO (conform).
        #
        # La superficie de guia es un plano: por bien que lo coloques,
        # atraviesa el morro en diagonal y solo lo toca en cuatro sitios. Y
        # eso rompe el wrap de las dos maneras a la vez:
        #
        #   falloff corto -> solo pesan los vertices que la tocan. Se los
        #                    lleva enteros: pinchazos en las comisuras.
        #   falloff largo -> pesa TODO a 1, incluida media cabeza: papilla.
        #
        # No hay radio que cubra el labio sin cubrir la cara, porque el
        # problema no es el radio: es que la superficie no esta donde esta
        # el labio. Medido en el caballo: los 1200 vertices mas cercanos
        # estaban a una mediana de 25 unidades de la lamina.
        #
        # A True, cada CV se proyecta al punto mas cercano de la malla antes
        # de skinnear. La lamina deja de ser un plano que corta la cabeza y
        # pasa a ser una piel por encima del labio. A partir de ahi el
        # falloff ya significa algo: una meseta fina que cubre el grosor del
        # labio y una rampa que muere antes de llegar al ojo.
        #
        # Secundario pero gratis: la caja de la superficie se encoge, y como
        # el recorte a la region se filtra por esa caja, empieza a recortar
        # de verdad en vez de coger el caballo entero.
        self.wrap_conform = True
        # Cuanto se separa de la malla, a lo largo de la normal. 0 = justo
        # encima. Negativo la hunde un poco dentro, que suele dar una
        # deformacion mas limpia en las comisuras.
        self.wrap_conform_offset = 0.0

        # UN DEFORMER POR LABIO.
        #
        # El montaje anterior era UN proximityWrap con un driver por lamina.
        # No vale, y el motivo es estructural: un proximityWrap tiene UN SOLO
        # set de deformacion, asi que la membresia es compartida y por driver
        # solo puedes tocar el falloff. Quien se lleva cada vertice lo decide
        # maxDrivers:
        #
        #   maxDrivers 2 -> las dos laminas compiten en las comisuras y Maya
        #                   normaliza entre ambas: papilla justo donde mas se
        #                   nota.
        #   maxDrivers 1 -> cada vertice elige la lamina mas CERCANA. Parte el
        #                   morro, pero lo parte mal: con la boca cerrada los
        #                   labios se tocan, y vertices del labio de abajo
        #                   caen mas cerca de la NURBS de arriba y se van con
        #                   ella.
        #
        # A True se crea un deformer por pareja y a cada uno se le da SU
        # lista de vertices. El reparto deja de ser un efecto secundario de
        # la distancia y pasa a estar escrito. Ademas cada labio queda con su
        # propio mapa de pesos, que se puede pintar para rematar la comisura.
        #
        # No cuesta el doble: cada deformer evalua solo su mitad, asi que el
        # trabajo total es el mismo o menos que un deformer sobre la union.
        self.wrap_split_by_pair = True
        # Margen del desempate. Si las dos distancias se parecen en menos de
        # esta fraccion, no decide la distancia (poco fiable con los labios
        # pegados) sino de que lado de la boca cae el vertice.
        self.wrap_split_ambiguous = 0.35

        # LIMITAR EL DEFORMER AL MORRO.
        #
        # Un proximityWrap evalua TODOS los vertices del objeto al que se le
        # pone. En el caballo entero son decenas de miles, y para cada uno
        # busca el punto mas cercano de la NURBS: por eso se arrastra.
        #
        # A True, el deformer se crea solo sobre los vertices que caen cerca
        # de la NURBS. Los demas ni se miran, y es la diferencia entre que
        # vaya a tirones o no se note.
        self.wrap_limit_to_region = True
        # Margen alrededor de la NURBS al elegir esos vertices, SOBRE el
        # alcance real (falloffEnd * falloffScale). 1.5 = un 50% de colchon,
        # para que la deformacion llegue a cero antes del borde del set y no
        # se vea el corte.
        self.wrap_region_margin = 1.5

        # EL CAGE DE POLIGONOS.
        #
        # Medido en el caballo: con las NURBS conectadas directamente, mover
        # un control costaba 209 ms. Con un cage de malla por medio, 34. Seis
        # veces, y no es casualidad: con un driver NURBS el deformer resuelve
        # el punto mas cercano sobre una superficie parametrica para CADA
        # vertice, que es un calculo iterativo sin estructura de aceleracion
        # posible (de ahi que exista spanSamples, un apano para aproximarlo
        # muestreando). Con una malla usa su arbol espacial.
        #
        # Por eso el ejemplo del manual de Maya usa un cage de poligonos.
        #
        # Las NURBS NO desaparecen: siguen siendo las que llevan el skin y
        # las que se deforman. El cage es una conversion VIVA de cada una
        # (nurbsToPoly con historial), asi que se mueve con ellas sin que
        # haya que pintar nada dos veces.
        self.wrap_use_cage = True
        self.wrap_cage_u = 10        # divisiones de la conversion
        self.wrap_cage_v = 6

        # Un diccionario por superficie, con sus dos NURBS y sus dos cages:
        #   {"label", "guide", "reference", "driver",
        #    "reference_geo", "driver_geo", "cluster"}
        self.wrap_pairs = []

        # ==========================================================
        # EL REBUZNO
        # ----------------------------------------------------------
        # Un atributo en un control de la boca que dobla los CVs DE ABAJO de
        # la NURBS Def. Al doblarse, la Def deja de coincidir con la Ref, y
        # esa diferencia es lo que el wrap le pasa al morro.
        #
        # Es un cluster y una multiplicacion: ni blendShapes, ni targets, ni
        # geometria de mas. Y queda como un canal normal en el channel box,
        # asi que cualquier UI o picker lo puede exponer sin saber nada de
        # como esta montado por dentro.
        #
        # El cluster lleva el PIVOTE en la fila de arriba, no en su centro:
        # asi el labio se ENROLLA sobre si mismo en vez de desplazarse en
        # bloque, que es lo que hace de verdad un morro al rebufar.
        self.wrap_snort_attr = "Rebuzno"
        # Control donde vive el canal. None = el centro del labio de abajo.
        self.wrap_snort_control = None
        # Filas de CVs desde abajo que entran, y cuanto pesa cada una (la de
        # mas abajo, entera; las de arriba, menos).
        # Filas de CV que se curvan. Con 2 el rizo salia de 3.42 unidades
        # como maximo en toda la lamina (medido): no daba para un rebuzno.
        # Topes del atributo. None = sin limites, que es lo comodo para
        # buscar el recorrido. (0, 1) o lo que sea para acotarlo.
        self.wrap_snort_limits = None
        # ANCHO del rizo, a lo largo del labio. El peso del cluster
        # caia solo por FILAS, asi que todos los CV de una fila giraban
        # igual, comisuras incluidas: como ademas rotan alrededor de un
        # pivote unico, los de los extremos tienen el brazo de palanca
        # mas largo y salian disparados como pinchos.
        #
        # Ahora el peso cae tambien a lo ancho: maximo en el centro del
        # morro y cero en las comisuras, que es como se enrolla el labio
        # de verdad. 1.0 = el rizo llega hasta la comisura; 0.6 = se
        # queda en el centro del morro.
        self.wrap_snort_width = 0.8
        # PIVOTE COMPARTIDO. Cada labio tenia su bisagra en su propia
        # fila, asi que enrollaban desde alturas distintas y la boca se
        # abria descuadrada. A True los dos pivotan desde el mismo
        # punto: la media de las dos bisagras, o sea la linea de la
        # boca. El de abajo sube un poco y el de arriba baja, que es
        # exactamente lo pedido.
        self.wrap_snort_shared_pivot = True
        self.wrap_snort_rows = 3
        self.wrap_snort_falloff = 0.45
        # Grados de giro con el atributo a 1. Si enrolla al reves, se cambia
        # el signo en el input2 del nodo, que esta a la vista en el rig.
        self.wrap_snort_rotate = (55.0, 0.0, 0.0)

        self.wrap_snort_cluster = None
        self.wrap_skin = None
        self.wrap_nodes = []         # los proximityWrap creados

    # ------------------------------------------------------------------
    # UTILIDADES
    # ------------------------------------------------------------------
    def _guide_transform(self, guide, side):
        """
        Posicion y orientacion mundiales de una guia. Para el lado R, el
        espejo se construye a mano, eje por eje.

        POR QUE A MANO
        --------------
        Un espejo puro en X da un marco de ejes zurdo, y un zurdo no se puede
        escribir con una rotacion: una rotacion siempre deja el marco diestro.
        La version anterior metia la matriz bajo un grupo con scaleX = -1 y le
        preguntaba a Maya la rotacion en mundo. Maya tiene que partir esa
        matriz en rotacion + escala negativa, y decide el solo en que eje pone
        el -1. La rotacion que salia no era un espejo de nada: por eso los
        controles R no se movian en espejo.

        LO QUE SE HACE AHORA
        --------------------
        Con m(v) = (-vx, vy, vz) el reflejo de un vector en el plano YZ, el
        grupo del control R se orienta con

            x_R = -m(x_L)      y_R = m(y_L)      z_R = m(z_L)

        que SI es diestro (reflejar invierte la mano, negar un eje la vuelve a
        invertir), o sea una rotacion normal que Maya escribe sin trampas. El
        eje X que falta por reflejar lo pone el grupo _mirror_GRP con
        scaleX = -1 que _make_control mete debajo del grupo raiz. Resultado: el
        control R es el reflejo exacto del L, y los mismos valores en los dos
        lados dan movimientos en espejo en los tres ejes.

        Devuelve (posicion, rotacion) o (None, None).
        """
        if not cmds.objExists(guide):
            cmds.warning(f"[SimpleMouth] No existe la guia '{guide}'.")
            return None, None

        position = cmds.xform(guide, q=True, ws=True, t=True)
        rotation = cmds.xform(guide, q=True, ws=True, ro=True)

        if side != "R":
            return position, rotation

        m = cmds.xform(guide, q=True, ws=True, matrix=True)
        x_axis, y_axis, z_axis = m[0:3], m[4:7], m[8:11]

        x_r = [x_axis[0], -x_axis[1], -x_axis[2]]     # -m(x)
        y_r = [-y_axis[0], y_axis[1], y_axis[2]]      #  m(y)
        z_r = [-z_axis[0], z_axis[1], z_axis[2]]      #  m(z)
        t_r = [-position[0], position[1], position[2]]

        mirrored = (x_r + [0.0] + y_r + [0.0] + z_r + [0.0] + t_r + [1.0])

        # Un transform temporal SIN escalas negativas: la matriz ya es una
        # rotacion propia, asi que Maya la descompone sin ambiguedad.
        temp = cmds.group(em=True, n="tempMirrorTRN")
        cmds.xform(temp, ws=True, matrix=mirrored)
        position = cmds.xform(temp, q=True, ws=True, t=True)
        rotation = cmds.xform(temp, q=True, ws=True, ro=True)
        cmds.delete(temp)

        return position, rotation

    def _make_control(self, name, position, rotation=None, normal=(0, 0, 1),
                      mirrored=False, style=None):
        """
        Un control en una posicion, con su jerarquia GRP/SPC/OFF/SDK/ANIM.

        Args:
            style: clave de self.styles ("mid", "corner", "levator"...). Si no
                esta en el diccionario se usa DEFAULT_STYLE.

        Devuelve (control, grupo_raiz). Se usa controlsLibrary si esta; si no,
        un circulo, para que el modulo se pueda probar suelto.
        """
        if cmds.objExists(name):
            cmds.delete(name)

        lib_name = self.styles.get(style, self.DEFAULT_STYLE)
        scale = self.style_scales.get(style, self.DEFAULT_STYLE_SCALE)

        control = None
        if controlsLibrary is not None:
            try:
                control = controlsLibrary.create_control_from_lib(
                    lib_name=lib_name, final_name=name, scale=scale
                )
            except Exception as error:
                cmds.warning(f"[SimpleMouth] No he podido crear '{name}' con la "
                             f"forma '{lib_name}': {error}")
                control = None

        if control is None:
            control = cmds.circle(n=name, nr=normal, r=self.control_size,
                                  ch=False)[0]

        # Antes de meterlo en la jerarquia: los CVs van en espacio de objeto,
        # asi que el desplazamiento viaja con el control cuando el GRP se
        # coloca sobre la guia.
        self._offset_control_cvs(control, style)

        # Un locator temporal como destino del match: create_rig_hierarchy
        # espera un nodo, no una posicion.
        target = cmds.spaceLocator(n=f"{name}_tempTarget")[0]
        cmds.xform(target, ws=True, t=position)
        if rotation is not None:
            cmds.xform(target, ws=True, ro=rotation)

        # match_rotation a True: los controles (y con ellos sus joints) heredan
        # la orientacion de la guia. Antes salian alineados al mundo y no
        # coincidian con las guias, que es lo que se veia.
        group = self.groups.create_rig_hierarchy(
            control, target, match_rotation=rotation is not None,
            world_space=True
        )

        cmds.delete(target)

        self.output_nodes[control] = control

        if mirrored:
            self._insert_mirror(control, group)

        return control, group

    def _offset_control_cvs(self, control, style):
        """
        Aparta los CVs de la shape de un control, sin tocar su transform.

        Se recorren las shapes una a una en vez de usar "control.cv[*]":
        algunos controles de la libreria llevan mas de una curva, y esa
        sintaxis solo alcanza a la primera.
        """
        offset = self.style_cv_offsets.get(style)
        if not offset or not any(offset):
            return None

        if self.scale_cv_offsets and controlsLibrary is not None:
            try:
                rig_scale = controlsLibrary.get_rig_scale()
            except Exception:
                rig_scale = 1.0
            offset = tuple(value * rig_scale for value in offset)

        shapes = cmds.listRelatives(control, shapes=True,
                                    type="nurbsCurve") or []
        if not shapes:
            return None

        for shape in shapes:
            cmds.move(offset[0], offset[1], offset[2], f"{shape}.cv[*]",
                      relative=True, objectSpace=True)

        return offset

    def _insert_mirror(self, control, group):
        """
        Mete el reflejo en X dentro de la jerarquia del control R.

            GRP              <- constraints (marco diestro, sin tocar)
              _mirror_GRP    <- scaleX = -1   (NUEVO)
                SPC > OFF > SDK > ANIM > CTRL
                                          _out_TRN  <- scaleX = -1 (NUEVO)

        El reflejo va DEBAJO del GRP y no encima: un parentConstraint no sabe
        escribir un reflejo, asi que si el nodo constreñido estuviera dentro de
        un espacio negativo, el constraint devolveria orientaciones raras.
        Asi el GRP sigue siendo un transform normal y los constraints trabajan
        como siempre.

        El _out_TRN deshace el reflejo para todo lo que tenga que LEER este
        control desde fuera: el joint (un joint con escala negativa invierte
        las normales del skin) y los constraints de otros controles que usan
        este como padre. Nadie fuera del control ve nunca la escala -1.
        """
        base = control[:-len("_CTRL")] if control.endswith("_CTRL") else control
        spc = f"{base}_SPC"

        if not cmds.objExists(spc):
            cmds.warning(f"[SimpleMouth] No encuentro '{spc}', "
                         f"'{control}' se queda sin espejo.")
            return None

        mirror = cmds.group(em=True, n=f"{base}_mirror_GRP", parent=group)
        cmds.setAttr(f"{mirror}.scaleX", -1)

        # relative=True: el SPC conserva sus valores locales (identidad). Sin
        # esto, cmds.parent compensaria la escala del nuevo padre y el reflejo
        # se anularia en el propio SPC.
        cmds.parent(spc, mirror, relative=True)

        out = cmds.group(em=True, n=f"{base}_out_TRN", parent=control)
        cmds.setAttr(f"{out}.scaleX", -1)
        self.output_nodes[control] = out

        return mirror

    def _out(self, control):
        """
        Nodo que hay que usar para LEER un control desde fuera.

        En el lado L es el propio control. En el R es su _out_TRN, que tiene la
        misma posicion y un marco diestro. Ningun joint ni constraint debe
        apuntar al control R directamente.
        """
        return self.output_nodes.get(control, control)

    def _make_joint(self, name, control):
        """
        Joint en la posicion del control y constreñido a el.

        parentConstraint y scaleConstraint: el joint es un pasajero del control
        y no tiene vida propia.
        """
        if cmds.objExists(name):
            cmds.delete(name)

        driver = self._out(control)

        cmds.select(clear=True)
        joint = cmds.joint(n=name)
        cmds.matchTransform(joint, driver, pos=True, rot=True)

        cmds.parentConstraint(driver, joint, mo=False)
        cmds.scaleConstraint(driver, joint, mo=False)

        cmds.select(clear=True)

        # Se guardan porque el proximityWrap necesita la lista entera para
        # skinear la NURBS. Antes self.joints se quedaba siempre vacio.
        self.joints[name] = joint

        return joint

    def _blend_constraint(self, driver_a, driver_b, target, weight_a,
                          skip_translate=False):
        """
        parentConstraint de dos targets con pesos, en Shortest.

        interpType 2 (Shortest) no es opcional: el valor por defecto (Average)
        promedia angulos de Euler, y promediar 179 con -179 da 0 en vez de 180.
        Ahi es donde salen los saltos.
        """
        kwargs = {"mo": True}
        if skip_translate:
            kwargs["skipTranslate"] = ["x", "y", "z"]

        constraint = cmds.parentConstraint(driver_a, driver_b, target, **kwargs)[0]

        aliases = cmds.parentConstraint(constraint, q=True, weightAliasList=True)
        cmds.setAttr(f"{constraint}.{aliases[0]}", weight_a)
        cmds.setAttr(f"{constraint}.{aliases[1]}", 1.0 - weight_a)
        cmds.setAttr(f"{constraint}.interpType", 2)

        return constraint

    # ------------------------------------------------------------------
    # CONSTRUCCION
    # ------------------------------------------------------------------
    def _build_mid(self, half):
        """
        El control del centro de un labio.

        Un solo control: lo conduce el jaw al 100% (el constraint se pone en
        attach_to_jaw, sobre su grupo raiz) y el animador anima el propio
        control, porque el constraint escribe en el grupo y no en los canales
        del control. No se pisan.
        """
        position, rotation = self._guide_transform(self.lip_mid, "L")
        if position is None:
            return None, None

        name = f"C_{self.rig_name}_lip{half}Mid_CTRL"
        # half vale "Upper" o "Lower", asi que la clave sale sola.
        control, group = self._make_control(name, position, rotation,
                                            style=f"mid{half}")

        self.mid_groups[half] = group
        self.controls[f"{half}Mid"] = control

        self._make_joint(f"C_{self.rig_name}_lip{half}Mid_JNT", control)

        return control, None

    def _build_corner(self, side):
        """
        La comisura. Es el segundo padre de toda la cadena, asi que se
        construye antes que los eslabones.

        Se cuelga entre los dos controles del jaw con un atributo UpperLower,
        que es lo que hace que al abrir la boca la comisura se quede a medio
        camino en vez de irse entera con la mandibula.
        """
        position, rotation = self._guide_transform(self.lip_end, side)
        if position is None:
            return None

        name = f"{side}_{self.rig_name}_lipCorner_CTRL"
        control, group = self._make_control(name, position, rotation,
                                            mirrored=(side == "R"),
                                            style="corner")

        self.corner_groups[side] = group

        self.controls[f"{side}Corner"] = control
        self._make_joint(f"{side}_{self.rig_name}_lipCorner_JNT", control)

        return control

    def _build_chain_link(self, half, side, key, mid_ctrl, corner_ctrl):
        """
        Un eslabon intermedio: control, joint y el constraint de dos padres.
        """
        guide = self.lip_in01 if key == "01" else self.lip_in02
        position, rotation = self._guide_transform(guide, side)
        if position is None:
            return None

        base_name = self.CHAIN_NAMES[half][key]
        name = f"{side}_{self.rig_name}_{base_name}_CTRL"

        # El estilo va por base_name, asi que cada eslabon puede llevar su
        # propia forma sin tocar nada mas.
        control, group = self._make_control(name, position, rotation,
                                            mirrored=(side == "R"),
                                            style=base_name)

        # Los padres se leen por su nodo de salida: el de la comisura R tiene
        # escala negativa y no puede ser target de un constraint a pelo.
        mid_ctrl = self._out(mid_ctrl)
        corner_ctrl = self._out(corner_ctrl)

        weight = self.CHAIN_WEIGHTS[key]

        if self.use_cascade:
            # Rotacion: igual que siempre, del blend de los dos padres.
            # La traslacion la pone _build_cascade_curve mas tarde.
            self._blend_constraint(mid_ctrl, corner_ctrl, group, weight,
                                   skip_translate=True)

            # BASE: el mismo blend, completo, en un transform aparte. Es donde
            # estaria el grupo sin cascada. Hace dos cosas: sirve de target
            # para dosificar la cascada con cascade_amount, y es el espacio
            # donde se suma lo que mueve el animador para colocar el CV.
            prefix = f"{side}_{self.rig_name}_{base_name}"
            base = cmds.group(em=True, n=f"{prefix}CascadeBase_TRN",
                              parent=self._get_cascade_group())
            cmds.matchTransform(base, group, pos=True, rot=True)
            self._blend_constraint(mid_ctrl, corner_ctrl, base, weight)

            # LOCAL: hijo de la base que copia el translate del control. Su
            # mundo es "base + lo que ha movido el animador", que es donde
            # tiene que ir el CV de este control. Lee el canal translate, no
            # el worldMatrix del control, asi que no depende del grupo que la
            # curva va a mover: no hay ciclo.
            # En el lado R el control se mueve dentro de un espacio reflejado
            # (su _mirror_GRP). El Local tiene que moverse en el MISMO espacio,
            # o el CV iria hacia un lado en X y el control hacia el otro, y el
            # NEG ya no cancelaria. Por eso lleva su propio reflejo delante.
            local_parent = base
            if side == "R":
                local_parent = cmds.group(em=True, parent=base,
                                          n=f"{prefix}CascadeMirror_GRP")
                cmds.setAttr(f"{local_parent}.scaleX", -1)

            local = cmds.group(em=True, n=f"{prefix}CascadeLocal_TRN",
                               parent=local_parent)
            cmds.connectAttr(f"{control}.translate", f"{local}.translate")

            self.cascade_links[(half, side, key)] = {
                "control": control,
                "group": group,
                "spc": f"{prefix}_SPC",
                "base": base,
                "local": local,
            }
        else:
            self._blend_constraint(mid_ctrl, corner_ctrl, group, weight)

        print(f"[SimpleMouth] {group}: {mid_ctrl} {weight:.2f} / "
              f"{corner_ctrl} {1.0 - weight:.2f}")

        self.controls[f"{side}{base_name}"] = control
        self._make_joint(f"{side}_{self.rig_name}_{base_name}_JNT", control)

        return control

    def _get_cascade_group(self):
        """Grupo donde viven las bases, las curvas y los followers."""
        name = f"C_{self.rig_name}_mouthCascade_GRP"
        if not cmds.objExists(name):
            cmds.group(em=True, n=name)

            # inheritsTransform a 0: este grupo NO hereda nada de sus padres.
            #
            # Aqui dentro viven nodos que reciben posiciones en MUNDO por
            # conexion directa: las curvas (decomposeMatrix -> controlPoints) y
            # los followers (pointOnCurveInfo.position -> translate). Una
            # conexion directa no compensa al padre. Si este grupo acaba dentro
            # de algo que se mueve (el mouth_GRP bajo la cabeza, o el global
            # del personaje), esas posiciones se aplicarian DOS veces: la que
            # ya traen en mundo, mas la del padre. Al mover el personaje, toda
            # la cascada se iria el doble de lejos.
            #
            # Con inheritsTransform a 0 el grupo se queda siempre en el origen
            # del mundo, este donde este en la jerarquia, y espacio de objeto
            # = mundo se cumple siempre.
            cmds.setAttr(f"{name}.inheritsTransform", 0)

        self.cascade_group = name
        return name

    @staticmethod
    def _nearest_parameter(curve, position):
        """Parametro del punto de la curva mas cercano a una posicion."""
        shape = cmds.listRelatives(curve, shapes=True)[0]
        node = cmds.createNode("nearestPointOnCurve")
        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{node}.inputCurve")
        cmds.setAttr(f"{node}.inPosition", *position)
        parameter = cmds.getAttr(f"{node}.parameter")
        cmds.delete(node)
        return parameter

    @staticmethod
    def _cv_influence(curve, index, parameter):
        """
        Cuanto se mueve el punto de la curva en 'parameter' si el CV 'index'
        se mueve una unidad.

        En una curva no racional, punto(u) = suma de N_j(u) * CV_j, asi que la
        respuesta es exactamente N_index(u): un numero fijo entre 0 y 1, el
        mismo para X, Y y Z. Se mide empujando el CV y mirando cuanto se mueve
        el punto, que es mas facil que evaluar la base a mano.
        """
        before = cmds.pointOnCurve(curve, pr=parameter, p=True)
        cmds.move(1, 0, 0, f"{curve}.cv[{index}]", r=True, ws=True)
        after = cmds.pointOnCurve(curve, pr=parameter, p=True)
        cmds.move(-1, 0, 0, f"{curve}.cv[{index}]", r=True, ws=True)
        return after[0] - before[0]

    def _build_cascade_curve(self, half, mid_ctrl, corner_controls):
        """
        La curva de un labio y todo lo que cuelga de ella.

        EL PROBLEMA DEL DOBLE MOVIMIENTO
        --------------------------------
        Si un eslabon sigue a una curva y ademas mueve un CV de esa misma
        curva, se mueve dos veces: el animador lo desplaza 1, su CV se desplaza
        1, la curva en su punto se desplaza k (su propia influencia, entre 0 y
        1), su grupo le sigue, y el control acaba en 1 + k. Por eso el sistema
        viejo tenia una curva distinta para cada control: cada uno iba sobre
        una curva que no conducia el mismo. Y por eso tenia PreBind.

        LA SALIDA: UN NEG
        -----------------
        Con una sola curva se compensa restando. Como k es un numero fijo
        (N_i(u_i), ver _cv_influence), el grupo se mueve exactamente
        k * cascade_amount * lo que mueve el animador. Asi que el SPC del
        control, que esta libre, recibe menos esa cantidad con un
        multiplyDivide. Es el truco del NEG de la infografia de RIVETS.

        El animador mueve 1 -> el control se mueve 1. Los vecinos, lo que les
        toque segun la curva. Eso es la cascada sin doble transformacion.
        """
        order = [("R", "corner"), ("R", "02"), ("R", "01"),
                 (None, "mid"),
                 ("L", "01"), ("L", "02"), ("L", "corner")]

        drivers = []
        for side, key in order:
            if key == "mid":
                drivers.append(mid_ctrl)
            elif key == "corner":
                drivers.append(corner_controls.get(side))
            else:
                link = self.cascade_links.get((half, side, key))
                drivers.append(link["local"] if link else None)

        if not all(drivers):
            cmds.warning(f"[SimpleMouth] Cascada {half}: hacen falta los dos "
                         f"lados completos. Se queda solo con constraints.")
            return None

        positions = [cmds.xform(d, q=True, ws=True, t=True) for d in drivers]

        curve_name = f"C_{self.rig_name}_lip{half}Cascade_CRV"
        if cmds.objExists(curve_name):
            cmds.delete(curve_name)
        curve = cmds.curve(d=3, p=positions, n=curve_name)
        cmds.parent(curve, self._get_cascade_group())
        shape = cmds.listRelatives(curve, shapes=True)[0]

        # 1. Parametro e influencia propia de cada eslabon. Tiene que ir ANTES
        #    de conectar los CVs, porque _cv_influence los empuja a mano.
        for index, (side, key) in enumerate(order):
            if key in ("mid", "corner"):
                continue
            link = self.cascade_links[(half, side, key)]
            link["parameter"] = self._nearest_parameter(curve, positions[index])
            link["k"] = self._cv_influence(curve, index, link["parameter"])

        # 2. Cada CV sigue a su control. El grupo de la curva esta en el
        #    origen, asi que espacio de objeto = mundo.
        for index, driver in enumerate(drivers):
            decompose = cmds.createNode(
                "decomposeMatrix", n=f"{curve}_cv{index:02d}_DCM")
            cmds.connectAttr(f"{driver}.worldMatrix[0]",
                             f"{decompose}.inputMatrix")
            cmds.connectAttr(f"{decompose}.outputTranslate",
                             f"{shape}.controlPoints[{index}]")

        # 3. Cada eslabon sigue a la curva, y su NEG le quita su propio empuje.
        for (h, side, key), link in self.cascade_links.items():
            if h != half:
                continue

            prefix = link["base"].replace("CascadeBase_TRN", "")

            info = cmds.createNode("pointOnCurveInfo",
                                   n=f"{prefix}Cascade_POCI")
            cmds.connectAttr(f"{shape}.worldSpace[0]", f"{info}.inputCurve")
            cmds.setAttr(f"{info}.parameter", link["parameter"])

            follower = cmds.group(em=True, n=f"{prefix}CascadeFollow_TRN",
                                  parent=self._get_cascade_group())
            cmds.connectAttr(f"{info}.position", f"{follower}.translate")

            # Posicion del grupo: mezcla entre sin cascada (base) y con
            # cascada (curva). mo=True absorbe que la curva de grado 3 no pasa
            # exactamente por los CVs de dentro.
            point = cmds.pointConstraint(link["base"], follower, link["group"],
                                         mo=True)[0]
            aliases = cmds.pointConstraint(point, q=True, weightAliasList=True)
            cmds.setAttr(f"{point}.{aliases[0]}", 1.0 - self.cascade_amount)
            cmds.setAttr(f"{point}.{aliases[1]}", self.cascade_amount)

            # NEG: el SPC resta lo que la curva ha empujado al grupo por culpa
            # del propio control.
            compensation = link["k"] * self.cascade_amount
            if cmds.objExists(link["spc"]) and compensation:
                neg = cmds.createNode("multiplyDivide", n=f"{prefix}Cascade_NEG")
                cmds.connectAttr(f"{link['control']}.translate", f"{neg}.input1")
                cmds.setAttr(f"{neg}.input2", -compensation, -compensation,
                             -compensation, type="double3")
                cmds.connectAttr(f"{neg}.output", f"{link['spc']}.translate")

            print(f"[SimpleMouth] {link['group']}: sigue a {curve} en "
                  f"u={link['parameter']:.3f}, influencia propia "
                  f"k={link['k']:.3f} (compensada)")

        return curve

    # ------------------------------------------------------------------
    # ORGANIZACION EN LA JERARQUIA DEL RIG
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_group(name, parent=None):
        """Grupo con ese nombre, creandolo si hace falta. Idempotente."""
        if not cmds.objExists(name):
            cmds.group(em=True, n=name)

        if parent and cmds.objExists(parent):
            current = cmds.listRelatives(name, parent=True)
            if not current or current[0] != parent:
                cmds.parent(name, parent)

        return name

    def _face_systems_root(self):
        """
        C_<rig>_face_GRP, bajo el rig_GRP. Aqui van los joints y las redes.

        Compartido con la boca, el jaw, los ojos, las cejas y el socket. El
        rig_GRP lo da rigRoot con get_rig_grp().
        """
        rig_grp = f"{self.rig_name}_rig_GRP"
        if self.root_instance is not None and hasattr(self.root_instance, "get_rig_grp"):
            rig_grp = self.root_instance.get_rig_grp()

        parent = rig_grp if cmds.objExists(rig_grp) else None

        return self._ensure_group(f"C_{self.rig_name}_face_GRP", parent)

    def _face_controls_root(self):
        """
        C_<rig>_faceControls_GRP, bajo el local_CTL.

        Es el grupo que lleva el parentConstraint desde el head_CTRL, el que
        pone el modulo de jaw. Colgando aqui, los controles siguen a la cabeza
        sin constraint propio.

        Y sin constraint propio a proposito: si cada modulo se constriñera por
        su cuenta, tendrias un constraint por modulo haciendo lo mismo y ese
        movimiento llegaria tambien a los joints de skin, que es lo que rompe
        el montaje de dos mallas. Controles arriba con la cabeza, joints
        quietos abajo.
        """
        local_ctl = f"{self.rig_name}_local_CTL"
        if self.root_instance is not None:
            local_ctl = getattr(self.root_instance, "localCtl", None) or local_ctl

        parent = local_ctl if cmds.objExists(local_ctl) else None

        return self._ensure_group(f"C_{self.rig_name}_faceControls_GRP", parent)

    def _warn_if_head_not_attached(self):
        """Avisa si el grupo de controles de cara no lo constriñe nadie."""
        group = self._face_controls_root()
        constraints = cmds.listRelatives(group, children=True,
                                         type="constraint") or []

        if not constraints:
            cmds.warning(f"[SimpleMouth] '{group}' no esta constreñido a "
                         f"nada: los controles no van a seguir a la cabeza. Lo "
                         f"constriñe el modulo de jaw; comprueba que esta en "
                         f"la receta.")

        return bool(constraints)

    def organize(self, group_name):
        """
        Reparte lo que el build deja suelto:

            C_<rig>_faceControls_GRP        (sigue a la cabeza)
               |- C_<rig>_mouth_GRP         los GRP de los controles

            C_<rig>_face_GRP                (sistemas, bajo rig_GRP)
               |- C_<rig>_mouthJoints_GRP   los joints de skin
               |- C_<rig>_mouthCascade_GRP  curvas, bases y followers

        El grupo de la cascada va a sistemas y NO a controles a proposito:
        dentro hay nodos que reciben posiciones en mundo por conexion directa
        (los controlPoints de las curvas y los followers), y una conexion
        directa no compensa al padre. Por eso ese grupo lleva ademas
        inheritsTransform a 0: este donde este, no hereda nada.

        Los GRP de los controles si van al grupo de cara, pero para ellos el
        emparentado es solo orden: todos llevan parentConstraint (a la
        mandibula o a sus dos padres), y un constraint compensa la matriz del
        padre. Siguen a la cabeza a traves del jaw, no a traves de este grupo.
        """
        control_roots = []
        for control in self.controls.values():
            node = control
            while True:
                parent = cmds.listRelatives(node, parent=True, type="transform")
                if not parent:
                    break
                node = parent[0]
            if node not in control_roots and node != self.cascade_group:
                control_roots.append(node)

        if control_roots:
            if cmds.objExists(group_name):
                cmds.delete(group_name)

            self.module_group = cmds.group(control_roots, n=group_name)
            self._ensure_group(self.module_group, self._face_controls_root())

        systems_root = self._face_systems_root()

        if self.cascade_group and cmds.objExists(self.cascade_group):
            self._ensure_group(self.cascade_group, systems_root)

        joints_grp = self._ensure_group(f"C_{self.rig_name}_mouthJoints_GRP",
                                        systems_root)

        for joint in cmds.ls(f"*_{self.rig_name}_*_JNT", type="joint") or []:
            if not joint.endswith("_JNT"):
                continue
            if not any(key in joint for key in
                       ("lipUpperMid", "lipLowerMid", "lipCorner",
                        "levator", "depresor", "upperPinch", "lowerPinch")):
                continue
            if not cmds.listRelatives(joint, parent=True):
                cmds.parent(joint, joints_grp)

        return self.module_group

    def attach_to_jaw(self):
        """
        Engancha la boca a la mandibula. Separado de build() a proposito.

        El orden de la receta puede construir la boca antes que el jaw, y estos
        constraints necesitan que los controles del jaw ya existan. build() lo
        intenta igual por si el jaw ya estaba; si no, build_module vuelve a
        llamar aqui desde _build_jaw.

        Es idempotente: si ya se engancho, no hace nada.
        """
        if self.attached_to_jaw:
            return True

        if not (cmds.objExists(self.jaw_upper_ctrl)
                and cmds.objExists(self.jaw_lower_ctrl)):
            return False

        # 1. Cada centro de labio, al 100% a su mitad de la mandibula.
        for half, group in self.mid_groups.items():
            if not group or not cmds.objExists(group):
                continue
            jaw_ctrl = (self.jaw_upper_ctrl if half == "Upper"
                        else self.jaw_lower_ctrl)
            cmds.parentConstraint(jaw_ctrl, group, mo=True)
            print(f"[SimpleMouth] {group} <- {jaw_ctrl} (100%)")

        # 2. Las comisuras, entre las dos mitades, con su atributo animable.
        for side, group in self.corner_groups.items():
            if not group or not cmds.objExists(group):
                continue

            control = self.controls.get(f"{side}Corner")
            constraint = self._blend_constraint(
                self.jaw_upper_ctrl, self.jaw_lower_ctrl, group,
                1.0 - self.corner_upper_lower
            )

            if self.corner_upper_lower_attr:
                if not cmds.objExists(f"{control}.UpperLower"):
                    cmds.addAttr(control, ln="UpperLower", at="double",
                                 min=0, max=1, dv=self.corner_upper_lower,
                                 k=True)

                aliases = cmds.parentConstraint(constraint, q=True,
                                                weightAliasList=True)
                reverse = cmds.createNode(
                    "reverse",
                    n=f"{side}_{self.rig_name}_lipCornerUpperLower_REV"
                )
                cmds.connectAttr(f"{control}.UpperLower", f"{reverse}.inputX")
                cmds.connectAttr(f"{reverse}.outputX",
                                 f"{constraint}.{aliases[0]}")
                cmds.connectAttr(f"{control}.UpperLower",
                                 f"{constraint}.{aliases[1]}")

            weight = 1.0 - self.corner_upper_lower
            print(f"[SimpleMouth] {group} <- {self.jaw_upper_ctrl} "
                  f"{weight:.2f} / {self.jaw_lower_ctrl} "
                  f"{self.corner_upper_lower:.2f}")

        self.attached_to_jaw = True

        return True

    # ------------------------------------------------------------------
    # PROXIMITY WRAP  (montaje de REFERENCE DRIVER)
    # ------------------------------------------------------------------
    @staticmethod
    def _deformed_shape(node):
        """La shape visible de un transform (la que NO es intermediate)."""
        shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                    fullPath=True) or []

        return shapes[0] if shapes else None

    def _ensure_wrap_guide(self, name, altura=0.0):
        """
        Una NURBS guia. Si no esta, se crea a partir de las guias del labio.

        La que sale es generica: un plano curvado delante de la boca, del
        ancho de la boca. SIRVE PARA VER EL SISTEMA, no para la toma final;
        para eso hay que arrimarla al morro CV a CV.
        """
        if cmds.objExists(name):
            return name

        if not (cmds.objExists(self.lip_mid) and cmds.objExists(self.lip_end)):
            cmds.warning(f"[SimpleMouth] No existe '{name}' ni las guias del "
                         f"labio para deducirla. Vuelve a crear las guias de "
                         f"la boca.")
            return None

        mid = cmds.xform(self.lip_mid, q=True, ws=True, t=True)
        end = cmds.xform(self.lip_end, q=True, ws=True, t=True)

        half = max(abs(end[0] - mid[0]), 0.5)

        surface = cmds.nurbsPlane(n=name, ax=(0, 1, 0),
                                  w=half * 3.0, lr=0.45, d=3, u=6, v=4,
                                  ch=False)[0]
        cmds.xform(surface, ws=True, t=[mid[0], mid[1] + altura, mid[2]])
        cmds.setAttr(f"{surface}.rotateX", 90)

        num_u = 6 + 3
        for column, depth in ((0, -half * 1.6), (1, -half * 0.8),
                              (num_u - 1, -half * 1.6), (num_u - 2, -half * 0.8)):
            cmds.select(f"{surface}.cv[{column}][0:*]", r=True)
            cmds.move(0, 0, depth, r=True)
        cmds.select(clear=True)

        if cmds.objExists("boca_guides_GRP"):
            cmds.parent(surface, "boca_guides_GRP")

        cmds.warning(f"[SimpleMouth] '{name}' no existia y la he creado "
                     f"generica sobre la boca. COLOCALA pegada al morro y "
                     f"vuelve a construir.")

        return surface

    @staticmethod
    def _wrap_label(guide):
        """Etiqueta corta para nombrar los nodos de una superficie."""
        base = guide.split("|")[-1]
        for sobra in ("mouth_wrap", "mouth_", "_NRB"):
            base = base.replace(sobra, "")

        return (base.strip("_") or "Wrap").capitalize()

    def _cleanup_previous_wrap(self):
        """
        Borra el wrap y las NURBS de una construccion anterior.

        NO ES OPCIONAL, y la razon es fea: si el montaje se queda a medias
        (una excepcion justo despues del cmds.deformer, por ejemplo), en la
        escena queda un proximityWrap SIN DRIVERS. Y uno sin drivers no se
        queda quieto: escupe basura y revienta la malla. Si encima la malla
        no tiene skinCluster, ese zombi es el unico deformer que hay y te
        comes la deformacion entera.

        Al reconstruir sin limpiar, Maya ademas renombra el nuevo con un
        numero al final y te quedas con los dos vivos a la vez.
        """
        doomed = set()

        for target in self.wrap_targets:
            if not cmds.objExists(target):
                continue
            # Cualquier proximityWrap en el historial de la malla, se llame
            # como se llame: los nuestros y los que quedaron a medias.
            doomed.update(cmds.ls(cmds.listHistory(target) or [],
                                  type="proximityWrap"))

        doomed.update(cmds.ls(f"C_{self.rig_name}_mouthWrap*_NRB") or [])
        doomed.update(cmds.ls(f"C_{self.rig_name}_mouthCage*_GEO") or [])
        doomed.update(cmds.ls(f"C_{self.rig_name}_{self.wrap_snort_attr}*_CLS*") or [])

        for node in sorted(doomed):
            if cmds.objExists(node):
                print(f"[SimpleMouth] Borrando resto de un build anterior: {node}")
                cmds.delete(node)

        return doomed

    def _build_wrap_pairs(self):
        """
        Por cada superficie de guia, SU PAREJA de NURBS mas sus cages.

            <label>Ref_NRB   la de REFERENCIA. Se mueve como los joints de la
                             boca y nada mas: el labio "normal".
            <label>Def_NRB   la de DEFORMACION. Lo mismo mas el rebufo.

        El wrap no mira ninguna por separado: mira la DIFERENCIA de cada
        pareja, y esa diferencia es lo unico que llega a la malla.

        Por que importa: todo lo que hacen las dos a la vez se cancela. El
        caballo gira la cabeza, abre la mandibula, camina... las dos hacen lo
        mismo, la resta da cero y el wrap no toca nada. La malla ya se mueve
        por su propio skin y no se duplica. Solo sobrevive lo que le hagas a
        la Def y no a la Ref.

        Recien construidas son iguales: la diferencia es CERO y el sistema
        queda montado pero inerte. Construir no cambia nada de lo que ya hay.

        Devuelve la lista de parejas.
        """
        self.wrap_pairs = []

        separacion = 0.0
        if len(self.wrap_surfaces) > 1 and cmds.objExists(self.lip_end):
            mid = cmds.xform(self.lip_mid, q=True, ws=True, t=True)
            end = cmds.xform(self.lip_end, q=True, ws=True, t=True)
            separacion = max(abs(end[0] - mid[0]), 0.5) * 0.6

        alturas = {0: separacion, 1: -separacion}

        for indice, guide in enumerate(self.wrap_surfaces):
            if not self._ensure_wrap_guide(guide, alturas.get(indice, 0.0)):
                continue

            label = self._wrap_label(guide)
            pareja = {"label": label, "guide": guide, "cluster": None}

            for papel in ("reference", "driver"):
                name = (f"C_{self.rig_name}_mouthWrap{label}"
                        f"{'Ref' if papel == 'reference' else 'Def'}_NRB")
                if cmds.objExists(name):
                    cmds.delete(name)

                surface = cmds.duplicate(guide, n=name)[0]
                if cmds.listRelatives(surface, parent=True):
                    surface = cmds.parent(surface, world=True)[0]
                cmds.makeIdentity(surface, apply=True, t=1, r=1, s=1, n=0)

                # ANTES de skinnear: el bind tiene que hacerse con la
                # superficie ya pegada al morro. Las dos salen de la misma
                # guia y el calculo es determinista, asi que Ref y Def
                # quedan identicas, que es la condicion para que la resta
                # de cero en reposo.
                if self.wrap_conform:
                    self._conform_wrap_surface(surface)

                pareja[papel] = surface

            if self.wrap_auto_skin:
                self._skin_wrap_pair(pareja)

            if self.wrap_use_cage:
                self._build_cage_pair(pareja)

            pareja.setdefault("reference_geo", pareja["reference"])
            pareja.setdefault("driver_geo", pareja["driver"])

            self.wrap_pairs.append(pareja)
            print(f"[SimpleMouth] Pareja '{label}': "
                  f"ref {pareja['reference']} | def {pareja['driver']}")

        return self.wrap_pairs

    def _conform_wrap_surface(self, surface, target=None):
        """
        Pega los CV de la superficie a la malla.

        Cada CV se manda al punto mas cercano de la geometria y se separa
        wrap_conform_offset a lo largo de la normal de ese punto. Son 30 o 40
        CV, asi que el coste es cero: se hace una vez, al construir.

        Se usa un closestPointOnMesh en vez de la API porque da la normal en
        el mismo nodo, y la normal es lo que permite hundir la lamina un pelo
        por dentro del labio en vez de dejarla clavada en la piel.

        OJO con el orden: esto va ANTES del skin. Si se conforma despues, el
        bindPreMatrix se calcula con la forma de plano y los pesos salen de
        la posicion equivocada.
        """
        target = target or next(
            (t for t in (self.wrap_targets or []) if cmds.objExists(t)), None)
        if not target:
            cmds.warning("[SimpleMouth] No hay malla a la que pegar "
                         f"{surface}: se queda como esta.")
            return False

        shape = target
        if cmds.nodeType(shape) != "mesh":
            formas = cmds.listRelatives(target, s=True, ni=True) or []
            shape = formas[0] if formas else None
        if not shape:
            cmds.warning(f"[SimpleMouth] '{target}' no tiene shape de malla.")
            return False

        cvs = cmds.ls(f"{surface}.cv[*][*]", fl=True) or []
        if not cvs:
            return False

        nodo = cmds.createNode("closestPointOnMesh",
                               n=f"{surface}_conform_CPM")
        cmds.connectAttr(f"{shape}.worldMesh[0]", f"{nodo}.inMesh")

        movidos = 0.0
        try:
            for cv in cvs:
                origen = cmds.pointPosition(cv, world=True)
                cmds.setAttr(f"{nodo}.inPosition", *origen)
                destino = cmds.getAttr(f"{nodo}.position")[0]
                normal = cmds.getAttr(f"{nodo}.normal")[0]

                final = [destino[i] + normal[i] * self.wrap_conform_offset
                         for i in range(3)]
                cmds.xform(cv, ws=True, t=final)
                movidos += sum((final[i] - origen[i]) ** 2
                               for i in range(3)) ** 0.5
        finally:
            cmds.delete(nodo)

        print(f"[SimpleMouth] {surface} pegado a {target}: "
              f"{len(cvs)} CV, desplazamiento medio "
              f"{movidos / max(len(cvs), 1):.2f} unidades.")
        return True

    def _build_cage_pair(self, pareja):
        """
        Convierte las dos NURBS de una pareja a malla, con historial vivo.

        Las dos conversiones llevan EXACTAMENTE los mismos parametros, asi
        que salen con topologia identica. Es imprescindible: el wrap resta
        una de otra punto a punto, y con topologias distintas la resta no
        significa nada.
        """
        cages = {}
        for papel, sufijo in (("reference", "Ref"), ("driver", "Def")):
            name = f"C_{self.rig_name}_mouthCage{pareja['label']}{sufijo}_GEO"
            if cmds.objExists(name):
                cmds.delete(name)

            try:
                result = cmds.nurbsToPoly(
                    pareja[papel], name=name, constructionHistory=True,
                    format=2, polygonType=1,
                    uType=3, uNumber=self.wrap_cage_u,
                    vType=3, vNumber=self.wrap_cage_v,
                    useChordHeight=False, useChordHeightRatio=False)
            except Exception as error:
                cmds.warning(f"[SimpleMouth] No he podido convertir "
                             f"{pareja[papel]} a malla ({error}). Esa pareja "
                             f"ira con la NURBS y sera MUCHO mas lenta.")
                return None

            cage = result[0]
            cmds.setAttr(f"{cage}.visibility", 0)
            cages[papel + "_geo"] = cage

        pareja.update(cages)

        print(f"[SimpleMouth] Cage '{pareja['label']}' de "
              f"{cmds.polyEvaluate(cages['driver_geo'], vertex=True)} vertices.")

        return cages

    def _env_joint(self, joint):
        """
        El joint de ENV que le corresponde a uno de la boca, o None.

        skinning_module duplica el esqueleto a una version de ENV y es esa la
        que deforma de verdad; los joints que crea este modulo son los del
        rig. Como no se la convencion exacta de nombres, se prueban las
        habituales y se avisa de lo que sale, para poder corregirlo.
        """
        short = joint.split("|")[-1]
        base = short[:-4] if short.endswith("_JNT") else short

        for pattern in (f"{short}_ENV", f"{base}_ENV", f"{base}_env_JNT",
                        f"{base}_ENV_JNT", f"*{base}*ENV*"):
            found = [node for node in (cmds.ls(pattern, type="joint") or [])
                     if node != joint]
            if found:
                return found[0]

        return None

    def _wrap_influences(self):
        """
        Los joints que skinean las NURBS: los de ENV si existen, y si no los
        del propio modulo.
        """
        joints = sorted(self.joints.values())
        if not joints:
            return []

        influences = []
        missing = []
        for joint in joints:
            env = self._env_joint(joint)
            influences.append(env or joint)
            if not env:
                missing.append(joint)

        if missing and len(missing) == len(joints):
            cmds.warning("[SimpleMouth] No encuentro ningun joint de ENV para "
                         "la boca: las NURBS se skinean a los joints del rig. "
                         "Si tu ENV usa otra convencion de nombres, dimela.")
        elif missing:
            cmds.warning(f"[SimpleMouth] Sin ENV para: {missing}. Esos van al "
                         f"joint del rig.")
        else:
            print(f"[SimpleMouth] Influencias de ENV encontradas: "
                  f"{len(influences)}.")

        return influences

    def _pair_influences(self, label):
        """
        Los joints que deben skinear la lamina de ESE labio.

        El fallo que esto arregla: las dos superficies se skineaban a los 12
        joints de la boca, asi que los controles de arriba movian tambien la
        lamina de abajo y al reves. La de arriba tiene que obedecer al labio
        de arriba, la de abajo al de abajo, y las COMISURAS a las dos: son la
        bisagra, y si solo tiraran de una la lamina se rasgaria ahi.

        El reparto sale de CHAIN_NAMES, que ya sabe que eslabon es de que
        mitad ('levator'/'upperPinch' arriba, 'depresor'/'lowerPinch'
        abajo), mas el lipUpperMid / lipLowerMid de cada una. No hay lista
        de nombres duplicada que se quede vieja al tocar el modulo.

        Criterio: se quita lo que es de la OTRA mitad. Todo lo demas se
        queda, corners incluidos. Al reves (quedarse solo con lo que
        reconozco) un joint con un nombre inesperado desapareceria sin
        avisar, y perder una influencia no se ve hasta que deforma mal.
        """
        todas = self._wrap_influences()
        if not todas or label not in self.CHAIN_NAMES:
            return todas

        ajenos = set()
        for mitad, eslabones in self.CHAIN_NAMES.items():
            if mitad == label:
                continue
            ajenos.update(n.lower() for n in eslabones.values())
            ajenos.add(f"lip{mitad}mid".lower())

        propios = set(n.lower() for n in self.CHAIN_NAMES[label].values())
        propios.add(f"lip{label}mid".lower())

        suyas = []
        fuera = []
        for joint in todas:
            corto = joint.split("|")[-1].lower()
            de_otro = any(token in corto for token in ajenos)
            de_este = any(token in corto for token in propios)
            if de_otro and not de_este:
                fuera.append(joint.split("|")[-1])
            else:
                suyas.append(joint)

        print(f"[SimpleMouth] '{label}' skinea a {len(suyas)} joints; fuera "
              f"los de la otra mitad: {fuera}")

        return suyas or todas

    def _skin_wrap_pair(self, pareja):
        """
        Skinea la lamina de deformacion y, si hace falta, la de referencia.

        Con wrap_use_reference_driver a True se skinean LAS DOS con los
        MISMOS pesos: la resta tiene que dar cero en reposo, o el morro se
        deformaria sin que nadie haya pedido nada.

        A False solo se skinea la de deformacion. La de referencia se queda
        quieta en reposo, que es precisamente lo que Maya espera en
        driverBindGeometry: la forma de partida contra la que medir. Asi la
        malla SIGUE a la lamina en vez de recibir solo la diferencia, y de
        paso esa mitad de la cadena deja de evaluarse en cada frame.
        """
        # SOLO los joints de su mitad (mas las comisuras): si se skinean las
        # dos laminas a toda la boca, los controles de arriba mueven tambien
        # la de abajo.
        joints = self._pair_influences(pareja.get("label"))
        if not joints:
            cmds.warning("[SimpleMouth] No hay joints de boca: las NURBS se "
                         "quedan sin skin.")
            return None

        if self.wrap_use_reference_driver:
            superficies = (pareja["reference"], pareja["driver"])
        else:
            superficies = (pareja["driver"],)

        skins = []
        for surface in superficies:
            skins.append(cmds.skinCluster(
                joints, surface, toSelectedBones=True, maximumInfluences=3,
                dropoffRate=4, n=f"{surface}_SKC")[0])

        if len(skins) > 1:
            # Los pesos del segundo se copian del primero: identicos de
            # salida, que es la condicion para que la resta de cero.
            cmds.copySkinWeights(sourceSkin=skins[0], destinationSkin=skins[1],
                                 noMirror=True,
                                 surfaceAssociation="closestPoint",
                                 influenceAssociation=("name", "closestJoint"))

        self.wrap_skin = skins[0]
        print(f"[SimpleMouth] '{pareja['label']}' skineada a {len(joints)} "
              f"joints ({'las dos laminas' if len(skins) > 1 else 'solo la de deformacion; la de referencia se queda en reposo'}).")

        return skins

    def _cv_grid(self, surface):
        """Posiciones de todos los CVs: grid[u][v] en espacio de mundo."""
        shape = cmds.listRelatives(surface, s=True, ni=True)[0]
        num_u = cmds.getAttr(f"{shape}.spansU") + cmds.getAttr(f"{shape}.degreeU")
        num_v = cmds.getAttr(f"{shape}.spansV") + cmds.getAttr(f"{shape}.degreeV")

        grid = [[cmds.pointPosition(f"{surface}.cv[{u}][{v}]", w=True)
                 for v in range(num_v)] for u in range(num_u)]

        return grid, num_u, num_v

    def _bottom_rows(self, surface):
        """
        Las filas de CVs de ABAJO, de la mas baja hacia arriba.

        Cual de los dos indices corre en vertical no se da por supuesto: la
        NURBS puede venir de la guia del modulo o estar modelada a mano con
        otra parametrizacion. Se mide el recorrido en Y de cada eje y gana el
        que mas suba.

        Devuelve [(lista de CVs, altura media), ...] ordenado de abajo arriba.
        """
        grid, num_u, num_v = self._cv_grid(surface)

        def media_y(puntos):
            return sum(p[1] for p in puntos) / float(len(puntos))

        filas_u = [[grid[u][v] for v in range(num_v)] for u in range(num_u)]
        filas_v = [[grid[u][v] for u in range(num_u)] for v in range(num_v)]

        recorrido_u = abs(media_y(filas_u[0]) - media_y(filas_u[-1]))
        recorrido_v = abs(media_y(filas_v[0]) - media_y(filas_v[-1]))

        if recorrido_u >= recorrido_v:
            filas = [([f"{surface}.cv[{u}][{v}]" for v in range(num_v)],
                      media_y(filas_u[u])) for u in range(num_u)]
        else:
            filas = [([f"{surface}.cv[{u}][{v}]" for u in range(num_u)],
                      media_y(filas_v[v])) for v in range(num_v)]

        return sorted(filas, key=lambda fila: fila[1])

    def build_snort(self):
        """
        Un cluster de rebuzno por superficie, cada uno con SU atributo.

        El de arriba cuelga de C_<rig>_lipUpperMid_CTRL y el de abajo de
        ...lipLowerMid_CTRL, para poder rizar los dos labios por separado.
        Los dos pivotan desde el mismo punto (ver wrap_snort_shared_pivot).

        Cada labio enrolla por su BORDE LIBRE, que no es el mismo en los dos:
        el de arriba lo tiene abajo y el de abajo lo tiene arriba. Por eso no
        vale con repetir la misma receta: la primera superficie coge sus
        filas de abajo y la segunda las de arriba.

        Devuelve la lista de handles creados.
        """
        if not self.wrap_pairs:
            return []

        # EL PIVOTE COMPARTIDO: la media de las bisagras de los dos labios,
        # para que enrollen desde la misma altura en vez de cada uno desde su
        # fila. Se calcula antes de crear ningun cluster, con las laminas
        # todavia en reposo.
        pivote = self._shared_snort_pivot() if self.wrap_snort_shared_pivot \
            else None

        handles = []
        for indice, pareja in enumerate(self.wrap_pairs):
            # La primera superficie es la de arriba y enrolla por abajo; la
            # segunda es la de abajo y enrolla por arriba.
            por_abajo = (indice % 2 == 0)

            # Un atributo POR LABIO, en su propio control de mid lip: asi se
            # puede rizar arriba y abajo por separado.
            control = self._snort_control(pareja)
            if not control:
                continue
            self._ensure_snort_attr(control)

            handle = self._snort_cluster(pareja, control, por_abajo, pivote)
            if handle:
                handles.append(handle)
                pareja["cluster"] = handle

        return handles

    def _snort_control(self, pareja):
        """
        El control que lleva el atributo de ESE labio.

        Por defecto su propio mid lip (C_<rig>_lipUpperMid_CTRL para la
        lamina de arriba, ...lipLowerMid_CTRL para la de abajo), que es donde
        el animador ya esta tocando ese labio. wrap_snort_control, si se
        pasa, manda sobre todos: util para dejar los dos en un solo sitio.
        """
        if self.wrap_snort_control:
            control = self.wrap_snort_control
        else:
            control = f"C_{self.rig_name}_lip{pareja['label']}Mid_CTRL"

        if not cmds.objExists(control):
            cmds.warning(f"[SimpleMouth] No existe {control}: '"
                         f"{pareja['label']}' se queda sin atributo de "
                         f"rebuzno.")
            return None

        return control

    def _ensure_snort_attr(self, control):
        """El atributo del rebuzno en ese control, si no lo tiene ya."""
        if cmds.attributeQuery(self.wrap_snort_attr, node=control,
                               exists=True):
            return f"{control}.{self.wrap_snort_attr}"

        # SIN min/max: el recorrido util depende de como quede la lamina en
        # cada personaje, y un tope de 1 obliga a reconstruir para probar un
        # rizo mas fuerte. Si lo quieres acotado para animacion, pasale
        # wrap_snort_limits=(min, max).
        cmds.addAttr(control, ln=self.wrap_snort_attr, at="float", dv=0, k=True)

        if self.wrap_snort_limits:
            minimo, maximo = self.wrap_snort_limits
            if minimo is not None:
                cmds.addAttr(f"{control}.{self.wrap_snort_attr}", e=True,
                             hasMinValue=True, minValue=minimo)
            if maximo is not None:
                cmds.addAttr(f"{control}.{self.wrap_snort_attr}", e=True,
                             hasMaxValue=True, maxValue=maximo)

        return f"{control}.{self.wrap_snort_attr}"

    def _snort_hinge(self, pareja, por_abajo):
        """
        El centro de la fila bisagra de una lamina: sobre esa linea enrolla.

        Es la primera fila que NO se mueve. Sin un pivote ahi el cluster
        desplaza el borde en bloque en vez de enrollarlo.
        """
        surface = pareja.get("driver")
        if not (surface and cmds.objExists(surface)):
            return None

        filas = self._bottom_rows(surface)
        if not por_abajo:
            filas = list(reversed(filas))
        if len(filas) < self.wrap_snort_rows + 1:
            return None

        bisagra = filas[self.wrap_snort_rows][0]
        posiciones = [cmds.pointPosition(cv, w=True) for cv in bisagra]
        if not posiciones:
            return None

        return [sum(pos[i] for pos in posiciones) / float(len(posiciones))
                for i in range(3)]

    def _shared_snort_pivot(self):
        """
        Un pivote para los dos labios: la media de sus bisagras.

        Cada lamina tenia la suya en su propia fila, a alturas distintas, y
        al rizar la boca se abria descuadrada. Promediandolas, el de abajo
        sube un poco y el de arriba baja hasta encontrarse en la linea de la
        boca, que es donde de verdad esta la bisagra del morro.
        """
        centros = []
        for indice, pareja in enumerate(self.wrap_pairs):
            centro = self._snort_hinge(pareja, indice % 2 == 0)
            if centro:
                centros.append(centro)

        if not centros:
            return None

        pivote = [sum(c[i] for c in centros) / float(len(centros))
                  for i in range(3)]
        print(f"[SimpleMouth] Pivote compartido del rebuzno: "
              f"({pivote[0]:.2f}, {pivote[1]:.2f}, {pivote[2]:.2f}) "
              f"de {len(centros)} bisagras.")
        return pivote

    def _snort_bell(self, u):
        """
        Cuanto riza el labio en la posicion u (0 a 1 a lo largo del labio).

        1 en el centro del morro, 0 en las comisuras, con un suavizado
        (smoothstep) para que no haya un escalon entre el CV que gira y el
        que no: un escalon ahi se ve como un pliegue duro en la geo.

        wrap_snort_width decide hasta donde llega: a 1.0 el rizo muere justo
        en la comisura, a 0.6 se queda en el centro del morro.
        """
        distancia = abs(2.0 * u - 1.0)          # 0 centro, 1 comisura
        ancho = max(self.wrap_snort_width, 1e-4)
        t = max(0.0, 1.0 - distancia / ancho)
        return t * t * (3.0 - 2.0 * t)          # smoothstep

    def _snort_cluster(self, pareja, control, por_abajo, pivote=None):
        """El cluster de una superficie. Ver build_snort."""
        surface = pareja.get("driver")
        if not (surface and cmds.objExists(surface)):
            return None

        filas = self._bottom_rows(surface)
        if not por_abajo:
            filas = list(reversed(filas))

        if len(filas) < self.wrap_snort_rows + 1:
            cmds.warning(f"[SimpleMouth] '{pareja['label']}' tiene muy pocas "
                         f"filas de CVs para el rebuzno.")
            return None

        usadas = filas[:self.wrap_snort_rows]
        cvs = [cv for fila, _ in usadas for cv in fila]

        name = f"C_{self.rig_name}_{self.wrap_snort_attr}{pareja['label']}"
        if cmds.objExists(f"{name}_CLSHandle"):
            cmds.delete(f"{name}_CLSHandle")

        cluster, handle = cmds.cluster(cvs, name=f"{name}_CLS")

        # Peso decreciente en los DOS sentidos: por filas (el borde libre
        # riza entero, las de dentro cada vez menos) y a lo ancho del labio
        # (maximo en el centro del morro, cero en las comisuras).
        for indice, (fila, _) in enumerate(usadas):
            peso_fila = self.wrap_snort_falloff ** indice
            ultimo = max(len(fila) - 1, 1)
            for columna, cv in enumerate(fila):
                u = columna / float(ultimo)
                cmds.percent(cluster, cv,
                             value=peso_fila * self._snort_bell(u))

        # EL PIVOTE: la bisagra sobre la que se enrolla el labio. Sin esto
        # el cluster desplaza el borde en bloque en vez de enrollarlo.
        #
        # Si viene uno compartido, ese: los dos labios tienen que pivotar
        # desde la misma altura o la boca se abre descuadrada.
        centro = pivote or self._snort_hinge(pareja, por_abajo)
        if centro:
            cmds.xform(handle, ws=True, pivots=centro)

        # El labio de arriba y el de abajo enrollan en sentidos opuestos.
        giro = list(self.wrap_snort_rotate)
        if not por_abajo:
            giro = [-v for v in giro]

        nodo = cmds.createNode("multiplyDivide", n=f"{name}_MDN")
        for eje in "XYZ":
            cmds.connectAttr(f"{control}.{self.wrap_snort_attr}",
                             f"{nodo}.input1{eje}")
        cmds.setAttr(f"{nodo}.input2", *giro, type="double3")
        cmds.connectAttr(f"{nodo}.output", f"{handle}.rotate", force=True)

        print(f"[SimpleMouth] Rebuzno '{pareja['label']}': {handle} "
              f"({len(cvs)} CVs, borde {'inferior' if por_abajo else 'superior'}, "
              f"giro {giro[0]:.0f}). Si enrolla al reves: {nodo}.input2X.")

        return handle

    def _set_wrap_mode(self, wrap_node):
        """
        Pone el modo por NOMBRE, no por numero.

        El indice de cada opcion del enum no esta documentado y puede cambiar
        entre versiones; el nombre no. Se le pregunta al propio nodo.
        """
        if not self.wrap_mode:
            return None

        try:
            opciones = (cmds.attributeQuery("wrapMode", node=wrap_node,
                                            listEnum=True) or [""])[0].split(":")
            indice = [o.lower() for o in opciones].index(self.wrap_mode.lower())
        except (ValueError, RuntimeError):
            cmds.warning(f"[SimpleMouth] {wrap_node} no tiene el modo "
                         f"'{self.wrap_mode}'. Se queda con el de por defecto.")
            return None

        cmds.setAttr(f"{wrap_node}.wrapMode", indice)
        print(f"[SimpleMouth] {wrap_node}: wrapMode = {self.wrap_mode}")

        return indice

    def _add_wrap_driver(self, wrap_node, index, driver_shape, reference_shape,
                         distance):
        """
        Engancha el par al proximityWrap, plug a plug.

            NURBS de deformacion.worldSpace -> drivers[0].driverGeometry
            NURBS de referencia.worldSpace  -> drivers[0].driverBindGeometry

        El segundo plug es el REFERENCE DRIVER del manual. Normalmente Maya
        mete ahi la forma original (la orig shape, quieta en bind pose) y el
        wrap transmite "cuanto se ha movido esto desde el principio". Metiendo
        otra version VIVA, lo que transmite es "cuanto se ha separado la una
        de la otra", que es lo que queremos.

        NO se usa maya.internal.nodes.proximitywrap: es codigo interno del
        Attribute Editor y cambia de version en version (en 2024 el
        NodeInterface ya no tiene addDriver). Los plugs del nodo si son
        publicos.
        """
        # Una malla saca su geometria por worldMesh y una NURBS por
        # worldSpace: el plug depende del tipo de shape, no es intercambiable.
        def salida(shape):
            tipo = cmds.nodeType(shape)
            return (f"{shape}.worldMesh[0]" if tipo == "mesh"
                    else f"{shape}.worldSpace[0]")

        plugs = {
            f"{wrap_node}.drivers[{index}].driverGeometry": salida(driver_shape),
            f"{wrap_node}.drivers[{index}].driverBindGeometry": salida(reference_shape),
        }

        for destination, source in plugs.items():
            if not cmds.objExists(destination):
                cmds.warning(f"[SimpleMouth] {wrap_node} no tiene "
                             f"'{destination.split('.', 1)[1]}'. Driver no "
                             f"conectado: revisa la version de Maya.")
                return False
            cmds.connectAttr(source, destination, force=True)

        # EL RADIO DE ACCION, por driver. Sin esto el deformer esta
        # conectado y no mueve nada: driverFalloffEnd vale 1.0 de serie, o
        # sea un radio de UNA unidad.
        # La meseta de peso 1. Sin ella el peso cae desde la propia
        # superficie y solo se mueve lo que la toca: ver el comentario de
        # wrap_falloff_start_ratio en __init__.
        if self.wrap_falloff_start is None:
            inicio = distance * self.wrap_falloff_start_ratio
        else:
            inicio = self.wrap_falloff_start
        # Maya no admite start >= end.
        inicio = min(inicio, distance * 0.95)

        cmds.setAttr(f"{wrap_node}.drivers[{index}].driverFalloffStart", inicio)
        cmds.setAttr(f"{wrap_node}.drivers[{index}].driverFalloffEnd", distance)

        print(f"[SimpleMouth] {wrap_node} driver {index}: falloff de "
              f"{inicio:.2f} (peso 1) a {distance:.2f} unidades.")

        return True

    def _auto_falloff_distance(self):
        """
        Radio de influencia a ojo: una fraccion del lado mayor de la NURBS.

        Escala solo con el personaje, que es lo que no hace el 1.0 que trae
        Maya. Si se queda corto o se come media cara, se pone a mano con
        wrap_falloff_distance.

        OJO con subirlo: el falloff no solo decide HASTA DONDE llega la
        deformacion, tambien CUANTOS vertices entran en el calculo. Pasarse
        aqui es la forma mas rapida de dejar la escena inanimable.
        """
        fuentes = [p.get("driver_geo") or p.get("driver")
                   for p in self.wrap_pairs]
        fuentes = [f for f in fuentes if f and cmds.objExists(f)]
        if not fuentes:
            return 1.0

        # El lado mayor de la mas grande: con dos labios, cada NURBS es mas
        # pequena que la unica de antes, y el falloff tiene que seguir
        # cubriendo el grosor del morro.
        mayor = 0.0
        for fuente in fuentes:
            box = cmds.exactWorldBoundingBox(fuente)
            mayor = max(mayor, box[3] - box[0], box[4] - box[1], box[5] - box[2])

        return mayor * self.wrap_falloff_ratio or 1.0

    @staticmethod
    def _deformer_set(wrap):
        """
        El objectSet de un deformer, o None.

        Un deformer NO se conecta a su set por una conexion normal: va por
        wrap.message -> objectSet.usedBy. Preguntando listConnections(wrap,
        type='objectSet') a secas no sale, y ese era el fallo: _restrict_
        membership no encontraba el set, se salia por el warning y el recorte
        no se aplicaba nunca. Con los dos deformers cubriendo la malla entera,
        cada vertice recibia las dos laminas: la mezcla entre NURBS.
        """
        # Por la API, que es el camino bueno: MFnGeometryFilter sabe cual
        # es su set sin depender de como este cableado.
        try:
            seleccion = om.MSelectionList()
            seleccion.add(wrap)
            filtro = oma.MFnGeometryFilter(seleccion.getDependNode(0))
            objeto = filtro.deformerSet
            if objeto and not objeto.isNull():
                return om.MFnDependencyNode(objeto).name()
        except Exception:
            pass

        # Por si acaso, las dos rutas por conexiones.
        for plug in (f"{wrap}.message", wrap):
            encontrados = cmds.listConnections(plug, type="objectSet") or []
            if encontrados:
                return encontrados[0]

        # Tercera via, al reves: en vez de preguntarle al deformer cual es su
        # set, se le preguntan a la GEOMETRIA todos sus sets de deformacion
        # (listSets type=2) y se mira cual dice pertenecer a este deformer
        # por su plug usedBy. No depende de la API ni de como este cableado
        # el message, que son las dos que han fallado aqui.
        for geo in cmds.deformer(wrap, q=True, g=True) or []:
            for candidato in cmds.listSets(object=geo, type=2) or []:
                duenos = cmds.listConnections(f"{candidato}.usedBy") or []
                if wrap in duenos:
                    return candidato

        # Si se llega aqui, que se vea con que esta conectado de verdad: es
        # lo unico que hace falta para cerrarlo.
        print(f"[SimpleMouth] No encuentro el set de {wrap}. Conectado a: "
              f"{cmds.listConnections(wrap, type='objectSet') or 'nada'} | "
              f"sets de la geo: "
              f"{cmds.listSets(object=(cmds.deformer(wrap, q=True, g=True) or [''])[0], type=2)}")

        return None

    @staticmethod
    def _vertex_indices(components):
        """
        Los indices de una lista de componentes, vengan sueltos o en rangos.

        _wrap_region los devuelve agrupados (vtx[10:450]) y _pair_regions
        sueltos (vtx[37]): hay que tragar las dos formas.
        """
        indices = []
        for componente in components or []:
            if ".vtx[" not in componente:
                continue
            dentro = componente.split("[")[1].rstrip("]")
            if ":" in dentro:
                a, b = dentro.split(":")
                indices.extend(range(int(a), int(b) + 1))
            else:
                indices.append(int(dentro))
        return indices

    @staticmethod
    def _as_vertex_ranges(target, indices):
        """
        Los indices, agrupados en rangos: vtx[10:450] en vez de 441 strings.

        Maya traga la lista larga, pero construirla y parsearla cuesta, y
        aqui pueden ser miles.
        """
        ranges = []
        start = previous = indices[0]

        for index in indices[1:]:
            if index == previous + 1:
                previous = index
                continue
            ranges.append((start, previous))
            start = previous = index
        ranges.append((start, previous))

        return [f"{target}.vtx[{a}]" if a == b else f"{target}.vtx[{a}:{b}]"
                for a, b in ranges]

    def _wrap_region(self, target, distance):
        """
        Los vertices de 'target' que estan cerca de la NURBS driver.

        Se filtran por la caja de la NURBS agrandada por el radio de
        influencia. Es una aproximacion grosera a proposito: comparar contra
        la superficie de verdad, vertice a vertice y en Python, tardaria mas
        que lo que ahorra. La caja sobra por los lados, y eso esta bien: mas
        vale coger de mas que cortar la deformacion por la mitad.

        Devuelve la lista de componentes, o None para no limitar nada.
        """
        fuentes = [p.get("driver_geo") or p.get("driver")
                   for p in self.wrap_pairs]
        fuentes = [f for f in fuentes if f and cmds.objExists(f)]
        if not fuentes:
            return None

        # El alcance REAL es driverFalloffEnd * falloffScale: el segundo
        # multiplica al primero. Sin contarlo, el recorte queda pegadisimo al
        # alcance y la deformacion se corta en seco en el borde del set.
        margin = distance * self.wrap_falloff_scale * self.wrap_region_margin

        # La caja que engloba TODAS las superficies: un vertice cerca de
        # cualquiera de ellas tiene que entrar.
        cajas = [cmds.exactWorldBoundingBox(f) for f in fuentes]
        low = [min(c[i] for c in cajas) - margin for i in range(3)]
        high = [max(c[i + 3] for c in cajas) + margin for i in range(3)]

        try:
            selection = om.MSelectionList()
            selection.add(target)
            dag = selection.getDagPath(0)
            # extendToShape NO es opcional: 'target' es el TRANSFORM, y
            # MFnMesh necesita la shape. Sin esto lanza excepcion, el except
            # se la traga, se devuelve None y el deformer acaba montado sobre
            # la malla entera. Justo lo que se queria evitar.
            if dag.apiType() == om.MFn.kTransform:
                dag.extendToShape()
            points = om.MFnMesh(dag).getPoints(om.MSpace.kWorld)
        except Exception as error:
            cmds.warning(f"[SimpleMouth] NO HE PODIDO LIMITAR EL WRAP a la "
                         f"zona del morro en {target} ({error}). Va a ir sobre "
                         f"la malla ENTERA y la escena se arrastrara.")
            return None

        inside = [i for i, point in enumerate(points)
                  if low[0] <= point.x <= high[0]
                  and low[1] <= point.y <= high[1]
                  and low[2] <= point.z <= high[2]]

        if not inside:
            cmds.warning(f"[SimpleMouth] Ningun vertice de {target} cerca de "
                         f"la NURBS. Esta colocada sobre el morro? El wrap ira "
                         f"sobre la malla entera.")
            return None

        print(f"[SimpleMouth] {target}: el wrap solo mira {len(inside)} de "
              f"{len(points)} vertices ({100.0 * len(inside) / len(points):.1f}%).")

        return self._as_vertex_ranges(target, inside)

    @staticmethod
    def _membership_count(wrap, target):
        """
        (vertices en el set del deformer, vertices totales).

        Cuando el deformer cubre el objeto entero, su set contiene la SHAPE y
        no componentes: por eso, si filterExpand no saca vertices, es que
        estan todos dentro.
        """
        total = cmds.polyEvaluate(target, vertex=True) or 0

        group = SimpleMouthModule._deformer_set(wrap)
        if not group:
            return total, total

        members = cmds.sets(group, q=True) or []
        vertices = cmds.filterExpand(members, selectionMask=31,
                                     expand=True) or []
        if vertices:
            return len(vertices), total

        # Sin componentes en el set es que esta la SHAPE entera dentro.
        return total, total

    def _pair_regions(self, target, parejas, distance):
        """
        Reparte los vertices de la region entre las parejas: a cada labio,
        los suyos.

        Para cada vertice se mide la distancia a la lamina de REFERENCIA de
        cada pareja (la de referencia, no la de deformacion: el reparto se
        decide en reposo, no con el rebuzno puesto) y se queda con la mas
        cercana.

        El desempate es lo importante. Con la boca cerrada los dos labios se
        tocan, asi que cerca de la comisura las dos distancias son casi
        iguales y la mas corta gana por ruido: de ahi que el labio de abajo
        se fuera con la NURBS de arriba. Cuando las dos distancias se
        parecen (menos de wrap_split_ambiguous de diferencia) se ignora la
        distancia y decide el LADO: por encima o por debajo de la linea de
        la boca, que es la frontera que de verdad queremos.

        Devuelve {indice de pareja: [componentes]}.
        """
        region = self._wrap_region(target, distance)
        if not region:
            return {}

        indices = self._vertex_indices(region)
        if not indices:
            return {}

        try:
            seleccion = om.MSelectionList()
            seleccion.add(target)
            dag = seleccion.getDagPath(0)
            if dag.apiType() == om.MFn.kTransform:
                dag.extendToShape()
            puntos = om.MFnMesh(dag).getPoints(om.MSpace.kWorld)
        except Exception as error:
            cmds.warning(f"[SimpleMouth] No puedo repartir los vertices de "
                         f"{target} ({error}).")
            return {}

        # Un nodo de consulta por pareja, y el centro de cada lamina para el
        # desempate por lado.
        consultas = []
        centros = []
        for pareja in parejas:
            geo = pareja.get("reference_geo") or pareja.get("reference")
            shape = self._deformed_shape(geo)
            if not shape:
                consultas.append(None)
                centros.append(0.0)
                continue

            if cmds.nodeType(shape) == "mesh":
                nodo = cmds.createNode("closestPointOnMesh")
                cmds.connectAttr(f"{shape}.worldMesh[0]", f"{nodo}.inMesh")
            else:
                nodo = cmds.createNode("closestPointOnSurface")
                cmds.connectAttr(f"{shape}.worldSpace[0]", f"{nodo}.inputSurface")
            consultas.append(nodo)

            caja = cmds.exactWorldBoundingBox(geo)
            centros.append((caja[1] + caja[4]) * 0.5)

        # La linea de la boca: el punto medio entre los centros de las dos
        # laminas. Con una sola pareja no hay nada que repartir.
        frontera = sum(centros) / max(len(centros), 1)

        reparto = {i: [] for i in range(len(parejas))}
        try:
            for indice in indices:
                punto = puntos[indice]
                distancias = []
                for nodo in consultas:
                    if nodo is None:
                        distancias.append(float("inf"))
                        continue
                    cmds.setAttr(f"{nodo}.inPosition", punto.x, punto.y, punto.z)
                    q = cmds.getAttr(f"{nodo}.position")[0]
                    distancias.append(((punto.x - q[0]) ** 2
                                       + (punto.y - q[1]) ** 2
                                       + (punto.z - q[2]) ** 2) ** 0.5)

                orden = sorted(range(len(distancias)), key=lambda k: distancias[k])
                mejor = orden[0]

                if len(orden) > 1:
                    primera, segunda = distancias[orden[0]], distancias[orden[1]]
                    ambiguo = (segunda - primera) <= max(primera, 1e-4) * \
                        self.wrap_split_ambiguous
                    if ambiguo:
                        # Empate tecnico: decide el lado de la boca.
                        arriba = punto.y >= frontera
                        candidatos = [k for k in (orden[0], orden[1])
                                      if (centros[k] >= frontera) == arriba]
                        if candidatos:
                            mejor = candidatos[0]

                reparto[mejor].append(f"{target}.vtx[{indice}]")
        finally:
            for nodo in consultas:
                if nodo and cmds.objExists(nodo):
                    cmds.delete(nodo)

        for i, pareja in enumerate(parejas):
            print(f"[SimpleMouth] Reparto '{pareja['label']}': "
                  f"{len(reparto[i])} vertices.")

        return reparto

    @staticmethod
    def _isolate_weights(wrap, dentro, total):
        """
        Peso 1 a los vertices de este labio, 0 al resto.

        Se escribe por TRAMOS (weights[a:b]) en vez de vertice a vertice: un
        setAttr por vertice sobre 18.000 vertices tarda una eternidad, y por
        tramos son cuatro llamadas.

        Esto aisla el deformer aunque su set siga cubriendo la malla entera.
        La membresia es la que ahorra tiempo de calculo; el peso es el que
        garantiza que no se mezclen las laminas. Hacen falta las dos, pero si
        solo se puede una, mejor esta.
        """
        if not total:
            return False

        try:
            tramos = []
            inicio = 0
            actual = 0 if 0 not in dentro else 1
            for i in range(1, total + 1):
                valor = None if i == total else (1 if i in dentro else 0)
                if valor != actual:
                    tramos.append((inicio, i - 1, actual))
                    inicio = i
                    actual = valor

            for a, b, valor in tramos:
                if a == b:
                    cmds.setAttr(f"{wrap}.weightList[0].weights[{a}]", valor)
                else:
                    cmds.setAttr(f"{wrap}.weightList[0].weights[{a}:{b}]",
                                 *([valor] * (b - a + 1)))
        except Exception as error:
            cmds.warning(f"[SimpleMouth] No he podido escribir los pesos de "
                         f"{wrap} ({error}).")
            return False

        print(f"[SimpleMouth] {wrap}: peso 1 en {len(dentro)} vertices, "
              f"0 en los otros {total - len(dentro)} ({len(tramos)} tramos).")
        return True

    def _restrict_membership(self, wrap, target, components):
        """
        Deja el deformer actuando SOLO sobre esos componentes.

        cmds.deformer(componentes, ...) ya deberia crearlo asi, pero segun el
        caso Maya acaba metiendo la malla entera en el set. Y cmds.sets con
        clear/forceElement no vale para un set de deformacion: hay que pasar
        por cmds.deformer en modo edicion, quitando la geometria y volviendo
        a anadir solo lo que interesa.

        Sin esto el deformer evalua los 18.000 vertices del caballo para
        mover los 900 del morro.
        """
        dentro = set(self._vertex_indices(components))
        total = cmds.polyEvaluate(target, vertex=True) or 0

        # 1. COMPONENT TAGS. Desde Maya 2022 un deformer guarda su membresia
        #    como una expresion de tag en el propio shape
        #    (input[0].componentTagExpression) y NO crea ningun objectSet. Por
        #    eso no aparecia por ninguna via: no existe. Si la expresion esta
        #    puesta, cmds.deformer(componentes, ...) ya recorto al crear el
        #    deformer y no hay NADA que tocar.
        try:
            expresion = cmds.getAttr(
                f"{wrap}.input[0].componentTagExpression") or ""
        except Exception:
            expresion = ""

        if expresion:
            print(f"[SimpleMouth] {wrap} recortado con component tags: "
                  f"'{expresion}' ({len(dentro)} vertices).")
            return len(dentro)

        # 2. El objectSet, para versiones que aun lo usen.
        conjunto = self._deformer_set(wrap)
        if not conjunto:
            # 3. Ni tag ni set: ahora SI hace falta el mapa de pesos, porque
            #    el deformer cubre la malla entera y sin peso 0 fuera de su
            #    mitad las dos laminas se mezclarian.
            #
            #    Va aqui y no antes a proposito. Estaba el primero y rompia la
            #    deformacion: los pesos se escriben por indice de vertice de
            #    la MALLA, pero cuando la membresia esta recortada el deformer
            #    solo ve sus vertices y su weightList va en SU orden, asi que
            #    los unos caian donde no tocaba y casi todo quedaba a cero.
            cmds.warning(f"[SimpleMouth] {wrap} no tiene ni component tag ni "
                         f"set: evalua la malla entera. Lo aislo con pesos.")
            self._isolate_weights(wrap, dentro, total)
            return 0

        # QUITAR LO QUE SOBRA, no vaciar y rellenar.
        #
        # Lo de antes era deformer -e -rm + deformer -e -g con los
        # componentes, y Maya en ese segundo paso vuelve a meter la malla
        # entera: de ahi el "18896 de 18896" aunque el deformer se creara con
        # una lista de vertices. Quitando el complemento el set nunca pasa
        # por vacio, que es lo que lo hacia recaer en la geometria completa.
        try:
            fuera = [i for i in range(total) if i not in dentro]
            if fuera:
                cmds.sets(self._as_vertex_ranges(target, fuera),
                          remove=conjunto)
        except Exception as error:
            cmds.warning(f"[SimpleMouth] No he podido recortar {wrap} "
                         f"({error}).")

        inside, total = self._membership_count(wrap, target)
        print(f"[SimpleMouth] {wrap} evalua {inside} de {total} vertices "
              f"({100.0 * inside / max(total, 1):.1f}%).")

        if inside >= total:
            cmds.warning(f"[SimpleMouth] {wrap} sigue sobre la malla ENTERA. "
                         f"Va a ir lento; revisa que la NURBS este colocada "
                         f"sobre el morro.")

        return inside

    def _configure_wrap(self, wrap, drivers):
        """Los ajustes comunes del nodo."""
        self._set_wrap_mode(wrap)
        cmds.setAttr(f"{wrap}.maxDrivers", drivers)
        cmds.setAttr(f"{wrap}.falloffScale", self.wrap_falloff_scale)
        cmds.setAttr(f"{wrap}.smoothInfluences", self.wrap_smooth_influences)
        if cmds.attributeQuery("spanSamples", node=wrap, exists=True):
            cmds.setAttr(f"{wrap}.spanSamples", self.wrap_span_samples)

    def _build_split_wraps(self, target, parejas, distance):
        """
        Un proximityWrap POR LABIO, cada uno con sus vertices.

        Asi el reparto esta escrito en la membresia en vez de salir de quien
        pilla mas cerca, que es lo que mandaba el labio de abajo a la NURBS
        de arriba. Cada deformer lleva un solo driver, su lamina.
        """
        reparto = self._pair_regions(target, parejas, distance)
        if not reparto:
            cmds.warning(f"[SimpleMouth] No he podido repartir {target} entre "
                         f"los labios: monto un solo deformer.")
            return self._build_single_wrap(target, parejas, distance)

        for indice, pareja in enumerate(parejas):
            componentes = reparto.get(indice) or []
            if not componentes:
                cmds.warning(f"[SimpleMouth] A '{pareja['label']}' no le ha "
                             f"tocado ningun vertice. Mira donde esta la guia "
                             f"{pareja['guide']}.")
                continue

            driver_shape = self._deformed_shape(pareja["driver_geo"])
            reference_shape = self._deformed_shape(pareja["reference_geo"])
            if not (driver_shape and reference_shape):
                cmds.warning(f"[SimpleMouth] La pareja '{pareja['label']}' no "
                             f"tiene shapes utilizables.")
                continue

            wrap = cmds.deformer(componentes, type="proximityWrap",
                                 n=f"{target}_mouth{pareja['label']}_PXW")[0]
            self._restrict_membership(wrap, target, componentes)
            # Un solo driver por deformer: no hay con quien competir.
            self._configure_wrap(wrap, 1)

            if self._add_wrap_driver(wrap, 0, driver_shape, reference_shape,
                                     distance):
                self.wrap_nodes.append(wrap)
                pareja["wrap"] = wrap
                print(f"[SimpleMouth] {wrap}: {len(componentes)} vertices del "
                      f"labio '{pareja['label']}'.")
            else:
                cmds.warning(f"[SimpleMouth] {wrap} sin driver: se borra.")
                cmds.delete(wrap)

    def _build_single_wrap(self, target, parejas, distance):
        """
        UN deformer con todas las laminas de driver.

        El montaje de antes. Se queda para una sola superficie, o si el
        reparto por labios falla: mejor un wrap compartido que ninguno.
        """
        region = (self._wrap_region(target, distance)
                  if self.wrap_limit_to_region else None)

        wrap = cmds.deformer(region or target, type="proximityWrap",
                             n=f"{target}_mouth_PXW")[0]
        if region:
            self._restrict_membership(wrap, target, region)
        self._configure_wrap(wrap, max(self.wrap_max_drivers, len(parejas)))

        conectados = 0
        for indice, pareja in enumerate(parejas):
            driver_shape = self._deformed_shape(pareja["driver_geo"])
            reference_shape = self._deformed_shape(pareja["reference_geo"])
            if not (driver_shape and reference_shape):
                cmds.warning(f"[SimpleMouth] La pareja '{pareja['label']}' no "
                             f"tiene shapes utilizables.")
                continue
            if self._add_wrap_driver(wrap, indice, driver_shape,
                                     reference_shape, distance):
                conectados += 1

        if conectados:
            self.wrap_nodes.append(wrap)
            print(f"[SimpleMouth] {wrap}: {target} con {conectados} drivers.")
        else:
            # Un wrap sin drivers deforma basura: antes que dejarlo, fuera.
            cmds.warning(f"[SimpleMouth] {wrap} no ha podido conectar ningun "
                         f"driver. Se borra para no dejar la malla rota.")
            cmds.delete(wrap)

    def build_proximity_wrap(self):
        """
        Monta el proximityWrap de la malla de la cara.

        UN SOLO DEFORMER con un DRIVER POR SUPERFICIE. Dos deformers
        encadenados costarian el doble y el segundo trabajaria sobre la
        malla ya deformada por el primero; con dos drivers, Maya resuelve
        las dos influencias en la misma pasada.

        Devuelve la lista de deformers creados.
        """
        if not self.use_proximity_wrap:
            return []

        targets = [t for t in self.wrap_targets if cmds.objExists(t)]

        for name in self.wrap_targets:
            if not cmds.objExists(name):
                cmds.warning(f"[SimpleMouth] No existe la malla '{name}'.")

        if not targets:
            cmds.warning("[SimpleMouth] El proximity wrap no tiene ninguna "
                         "malla que deformar. Pasale wrap_targets con el "
                         "nombre de la geometria de la cara.")
            return []

        # Fuera lo que quedara del build anterior, antes de nada.
        self._cleanup_previous_wrap()

        # El wrap pasa SOLO la resta entre cada par, asi que convive con el
        # skin de la malla sin duplicar nada. Y sin skin tambien funciona: la
        # malla se queda quieta y lo unico que se mueve es la deformacion.
        for target in targets:
            skins = cmds.ls(cmds.listHistory(target) or [], type="skinCluster")
            print(f"[SimpleMouth] {target}: "
                  f"{'con skinCluster ' + skins[0] if skins else 'SIN skinCluster'}.")

        # Las NURBS PRIMERO y el deformer despues: si algo falla montando las
        # parejas, no llega a crearse ningun proximityWrap y la malla se
        # queda como estaba en vez de con un zombi encima.
        parejas = self._build_wrap_pairs()
        if not parejas:
            cmds.warning("[SimpleMouth] Sin NURBS no se crea el deformer: la "
                         "malla se queda intacta.")
            return []

        distance = self.wrap_falloff_distance or self._auto_falloff_distance()

        self.wrap_nodes = []
        for target in targets:
            if self.wrap_split_by_pair and len(parejas) > 1:
                self._build_split_wraps(target, parejas, distance)
            else:
                self._build_single_wrap(target, parejas, distance)

        # El rebuzno: un cluster por superficie, todos al mismo atributo
        self.build_snort()

        # Las NURBS y los cages a sistemas: los mueven sus deformers, y un
        # padre que se mueva se lo sumaria otra vez.
        systems = self._face_systems_root()
        for pareja in parejas:
            for clave in ("reference", "driver", "reference_geo", "driver_geo"):
                node = pareja.get(clave)
                if node and cmds.objExists(node):
                    if cmds.objExists(systems):
                        self._ensure_group(node, systems)
                    cmds.setAttr(f"{node}.visibility", 0)

        return self.wrap_nodes

    def post_build(self):
        """
        Lo que tiene que esperar a que el resto del rig exista.

        De momento el proximity wrap, y por una razon de ORDEN: la boca se
        construye en el paso 50 y el skinning en el 70, asi que cuando corre
        build() los joints de ENV todavia no existen y las NURBS se
        skinearian a los joints del rig.

        build_module llama solo a este metodo en el paso 80 (_core_post),
        porque recorre los modulos construidos y ejecuta el post_build de
        quien lo tenga.
        """
        return self.build_proximity_wrap()

    def build(self):
        group_name = f"C_{self.rig_name}_mouth_GRP"
        if cmds.objExists(group_name):
            cmds.delete(group_name)

        self.controls = {}
        self.joints = {}
        self.cascade_links = {}
        self.output_nodes = {}
        self.wrap_nodes = []

        cascade_name = f"C_{self.rig_name}_mouthCascade_GRP"
        if cmds.objExists(cascade_name):
            cmds.delete(cascade_name)
        self.cascade_group = None

        # 1. Los centros de los dos labios. Son el primer padre de la cadena.
        mid_controls = {}
        for half in ("Upper", "Lower"):
            main_ctrl, _ = self._build_mid(half)
            mid_controls[half] = main_ctrl

        # 2. Las comisuras. Segundo padre, compartidas por las dos mitades.
        corner_controls = {}
        for side in self.sides:
            corner_controls[side] = self._build_corner(side)

        # 3. Los eslabones, que ya solo cuelgan de los dos anteriores.
        for half in ("Upper", "Lower"):
            mid_ctrl = mid_controls.get(half)
            if not mid_ctrl:
                continue

            for side in self.sides:
                corner_ctrl = corner_controls.get(side)
                if not corner_ctrl:
                    continue

                for key in ("01", "02"):
                    self._build_chain_link(half, side, key,
                                           mid_ctrl, corner_ctrl)

        # 3b. La cascada: una curva por labio. Va despues de los eslabones
        #     porque necesita sus bases ya creadas.
        if self.use_cascade:
            for half in ("Upper", "Lower"):
                if mid_controls.get(half):
                    self._build_cascade_curve(half, mid_controls[half],
                                              corner_controls)

        # 4. Repartir todo lo que quedo suelto en el mundo.
        self.organize(group_name)

        # El proximity wrap NO se monta aqui: ver post_build().

        # Si el jaw ya existe, se engancha ahora. Si no, lo hara build_module
        # cuando construya la mandibula.
        if not self.attach_to_jaw():
            cmds.warning("[SimpleMouth] Todavia no hay controles de jaw. "
                         "La boca queda montada pero sin seguir a la mandibula "
                         "hasta que se llame a attach_to_jaw().")

        print(f"[SimpleMouth] {len(self.controls)} controles y joints.")

        return self.module_group