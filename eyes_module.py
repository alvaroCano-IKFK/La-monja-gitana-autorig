import math

import maya.cmds as cmds    
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class EyesModule(object):

    # Rebuild de la linea del parpado: grado 3 con 4 spans = 7 CVs, que es el
    # numero al que corresponde CV_WEIGHTS. Si cambias esto, CV_WEIGHTS deja de
    # cuadrar.
    LINE_CURVE_SPANS = 4
    LINE_CURVE_DEGREE = 3

    # Parametros (en fraccion del rango de la linea) donde se muestrean las 5
    # posiciones de guia del parpado, de comisura interna a externa:
    # [esquina_interna, secundario_interno, centro, secundario_externo, esquina_externa]
    EYELID_GUIDE_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)

    # Pesos de cada CV de las curvas de los parpados.
    # Cada lista sigue el orden de influencias interna -> externa:
    # [esquina_interna, secundario_interno, centro, secundario_externo, esquina_externa]
    CV_WEIGHTS = {
        0: [1.0, 0.0, 0.0, 0.0, 0.0],
        1: [0.5931, 0.4069, 0.0, 0.0, 0.0],
        2: [0.0, 0.7595, 0.2405, 0.0, 0.0],
        3: [0.0, 0.0, 0.8949, 0.1051, 0.0],
        4: [0.0, 0.0, 0.2286, 0.7714, 0.0],
        5: [0.0, 0.0, 0.0, 0.4, 0.6],
        6: [0.0, 0.0, 0.0, 0.0, 1.0],
    }

    # Atributos de follow del grupo de settings:
    # (nombre_largo, nombre_visible, valor_por_defecto).
    #
    # El defecto es 0.7 y no 0.5 siguiendo el diagrama del documento, que marca
    # (0.3 / 0.7) en los intermedios. El atributo va al peso del driver A (el
    # parpado) y su reverse al del driver B (la esquina), asi que 0.7 = el
    # intermedio sigue mayormente al centro del parpado. Si en tu cara queda
    # mejor al reves, es cambiar este numero por 0.3.
    SETTINGS_ATTRIBUTES = [
        ("Up01FollowUp", "Up 01 Follow Up", 0.7),
        ("Up03FollowUp", "Up 03 Follow Up", 0.7),
        ("Low01FollowLow", "Low 01 Follow Low", 0.7),
        ("Low03FollowLow", "Low 03 Follow Low", 0.7),
    ]

    # Atributos extra del control del ojo:
    # (nombre_largo, nombre_visible, defecto, minimo, maximo).
    #
    # blinkHeight lleva su propio rango 0..1: es una altura de cierre y no tiene
    # lado negativo, a diferencia de los dos blink, que van de -1 (abrir) a 1
    # (cerrar). Antes los tres compartian min -1 y el blinkHeight se podia
    # meter en negativo.
    BLINK_ATTRIBUTES = [
        ("upperBlink", "Upper Blink", 0.0, -1.0, 1.0),
        ("lowerBlink", "Lower Blink", 0.0, -1.0, 1.0),
        ("blinkHeight", "Blink Height", 0.2, 0.0, 1.0),
    ]

    # Defecto del atributo de fleshy, segun el documento.
    FLESHY_DEFAULT = 0.1

    # Eje de rotacion del fleshy que NO se conecta. El documento pide que solo
    # se conecten DOS de los tres, dejando fuera el twist del ojo.
    #
    # Aqui el que se deja fuera es la Z: el parpado sigue la mirada girando en
    # X (arriba / abajo) y en Y (izquierda / derecha), que es el comportamiento
    # que se quiere. Ponlo a "X" o a "Y" si en otra cara el eje del twist cae
    # en otro sitio.
    FLESHY_SKIP_AXIS = "Z"

    # Cuanto se separan las curvas NegateBlink de su original, como fraccion del
    # radio del parpado. Es la pose de apertura de partida: 0.0 las deja como
    # copias exactas (peso sin efecto) y valores mayores abren mas el ojo.
    NEGATE_OFFSET = 0.25

    # Eje por el que apunta la cadena de aim. Es el primaryInputAxis del
    # aimMatrix, que se deja en su valor por defecto (1, 0, 0).
    LOOP_AIM_AXIS = "X"

    # Cuanto sigue el end de la cadena a la distancia real entre el centro del
    # ojo y el punto de la curva. A 1.0 el joint cae exactamente sobre el punto;
    # a 0.0 se queda a radio fijo, que es el comportamiento que abre el agujero.
    # Entre medias, sigue solo una parte del recorrido.
    LOOP_RADIUS_FOLLOW = 1.0

    # Margen del remap alrededor de la distancia en reposo, como fraccion de esa
    # distancia. Solo define hasta donde llega la rampa antes de clampear.
    LOOP_RADIUS_RANGE = 0.5

    # Atenuadores de cada setup de fleshy. Van al input2 del multDoubleLinear
    # que alimenta al blender, asi que el atributo del control sigue yendo de 0 a
    # 1 pero lo que llega de verdad es solo esta fraccion. Las esquinas estan
    # mucho mas ancladas que el centro del parpado, por eso van bajas.
    FLESHY_LIDS_MULT = 1.0
    FLESHY_CORNERS_MULT = 0.35

    # Si el fleshy tiene que llegar tambien al setup local que conduce los joints.
    # Ver _build_fleshy_setup para el porque.
    FLESHY_DRIVE_LOCAL = True

    # Corrige el signo de la traslacion del setup local en el lado R.
    #
    # Las guias del ojo derecho estan en mirror BEHAVIOUR respecto al
    # izquierdo: sus ejes son los del espejo de L pero negados, o sea que el
    # ojo derecho esta girado 180 grados sobre la X del mundo, no reflejado.
    # Esa convencion es la correcta para ROTACIONES (los mismos valores de
    # rotate dan movimientos simetricos) pero es la contraria para
    # TRASLACIONES, y este sistema mueve todo por traslacion: lee ctrl.matrix
    # y mete su outputTranslate en el _Local_TRN.
    #
    # En el body esto no se nota porque los controles viven dentro del
    # mirrorBehaviour_GRP y su scaleX = -1 arregla el signo. Aqui no sirve:
    # ctrl.matrix es LOCAL y no se entera de sus padres, y el _Local_OFF donde
    # se reaplica esta fuera de ese grupo.
    #
    # Como los ejes de R son los del espejo de L negados en los tres, la
    # correccion es negar las tres componentes. Se hace en la conexion y no
    # con un scale -1 en el OFF (que seria equivalente) para no meter escalas
    # negativas en los joints que skinean las curvas.
    #
    # Ponlo a False para volver al comportamiento de antes.
    MIRROR_R_TRANSLATION = True
    MIRROR_R_TRANSLATION_SIGN = (-1.0, -1.0, -1.0)

    # La otra mitad del mismo problema, esta vez en el lado del animador.
    #
    # Con MIRROR_R_TRANSLATION el sistema ya se mueve en espejo, pero el gizmo
    # del control sigue en orientacion de behaviour, asi que el control tira
    # hacia un lado y el parpado hacia el otro. La solucion es voltearle los
    # ejes al grupo del control con el mismo signo.
    #
    # scale y no rotate a proposito: la shape se dibuja alrededor del origen
    # del grupo, asi que el control no se mueve de sitio, solo cambian las
    # direcciones de sus canales.
    #
    # Y no afecta al sistema: lo que este lee es ctrl.matrix, que es la matriz
    # del control DENTRO de su _GRP y no se entera de la escala del grupo. El
    # _Local_OFF tampoco, porque se matcheo con posicion y rotacion.
    MIRROR_R_CONTROL_AXES = True
    MIRROR_R_CONTROL_SCALE = (-1.0, -1.0, -1.0)

    def __init__(self, 
                 eye_mid="eye_mid",
                 eye_inner_corner="eye_inner_corner",
                 eye_outer_corner="eye_outer_corner",
                 eyelid_up="eyelid_up",
                 eyelid_low="eyelid_low",
                 eyelid_up02="eyelid_up02",
                 eyelid_up03="eyelid_up03",
                 eyelid_low02="eyelid_low02",
                 eyelid_low03="eyelid_low03",
                 root_instance=None,   
                 rig_name="Character",
                 side="L",
                 eye_mid_end="eye_mid_end",
                 eye_direct="eye_direct",
                 upper_loop_curve=None,
                 lower_loop_curve=None,
                 upper_loop_count=None,
                 lower_loop_count=None,
                 upper_loop_set=None,
                 lower_loop_set=None):
        

        self.eye_mid = eye_mid
        self.eye_mid_end = eye_mid_end
        self.eye_direct = eye_direct
        self.eye_inner_corner = eye_inner_corner
        self.eye_outer_corner = eye_outer_corner

        self.eyelid_up = eyelid_up
        self.eyelid_low = eyelid_low

        self.eyelid_up02 = eyelid_up02
        self.eyelid_up03 = eyelid_up03

        self.eyelid_low02 = eyelid_low02
        self.eyelid_low03 = eyelid_low03

        self.group_maker = ControlsGroups()
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.styles = {"mainFk": "circleControl",
                       "eyelid":"eyelid",
                       "eyelidSub": "eyelidSub",}
        
        self.side = side
        self.prefix = f"{self.side}_{rig_name}"

        # Guias que llevan un segundo control (Sub) ademas del principal
        self.sub_control_guides = [
            self.eye_inner_corner,
            self.eye_outer_corner,
            self.eyelid_up,
            self.eyelid_low,
        ]

        # Setups de fleshy, cada uno con su atributo, su atenuador y su cadena
        # de grupos independiente. Los parpados y las esquinas van por separado
        # porque las esquinas se pasan de largo con el mismo valor.
        # Los intermedios (02 y 03) no aparecen: ya van constrainidos a estos y
        # les siguen solos.
        self.fleshy_setups = [
            {
                "key": "lids",
                "name": "eyeFleshy",
                "attribute": "fleshy",
                "nice_name": "Fleshy",
                "multiplier": self.FLESHY_LIDS_MULT,
                "guides": [self.eyelid_up, self.eyelid_low],
            },
            {
                "key": "corners",
                "name": "eyeFleshyCorners",
                "attribute": "fleshyCorners",
                "nice_name": "Fleshy Corners",
                "multiplier": self.FLESHY_CORNERS_MULT,
                "guides": [self.eye_inner_corner, self.eye_outer_corner],
            },
        ]

        # key -> {blend, multiplier, attribute, off, trn, local_off, local_trn}
        self.fleshy_nodes = {}

        # Guias intermedias: cada una queda entre dos guias que la conducen y
        # su reparto lo manda un atributo del grupo de settings.
        # {guia_intermedia: (guia_driver_A, guia_driver_B, atributo_de_follow)}
        # El atributo va directo al peso del driver A (el parpado) y pasa por un
        # reverse hacia el peso del driver B (la esquina).
        self.in_between_guides = {
            self.eyelid_up02: (self.eyelid_up, self.eye_inner_corner, "Up01FollowUp"),
            self.eyelid_up03: (self.eyelid_up, self.eye_outer_corner, "Up03FollowUp"),
            self.eyelid_low02: (self.eyelid_low, self.eye_inner_corner, "Low01FollowLow"),
            self.eyelid_low03: (self.eyelid_low, self.eye_outer_corner, "Low03FollowLow"),
        }

        # Joints creados a partir de las guias
        self.eye_joints = {}
        self.joints_group = None

        # Cadena de aim del ojo: eye_mid_end cuelga del joint de eye_mid, y el
        # control de eye_direct es el punto al que mira el ojo.
        self.eye_mid_end_joint = None
        self.eye_mid_joint_constraint = None
        self.eye_direct_control = None
        self.eye_direct_control_group = None
        self.eye_mid_aim_constraint = None

        # Curvas de los parpados
        self.upper_curve = None
        self.lower_curve = None
        self.upper_skin_cluster = None
        self.lower_skin_cluster = None

        # Sistema de blink
        self.blink_height_curve = None
        self.upper_blinked_curve = None
        self.lower_blinked_curve = None
        self.upper_negate_curve = None
        self.lower_negate_curve = None
        self.blink_blend_shapes = {}
        self.blink_curves_group = None

        # Controles y setup local
        self.eye_controls = {}
        self.eye_control_groups = {}
        self.eye_local_offs = {}
        self.eye_local_trns = {}
        self.eye_local_joints = {}

        # Segundos controles (Sub) y su setup local
        self.eye_sub_controls = {}
        self.eye_sub_control_groups = {}
        self.eye_sub_local_offs = {}
        self.eye_sub_local_trns = {}
        self.eye_sub_local_joints = {}

        # Joints de loop: uno por cada loop del parpado en la malla.
        #
        # El origen es la CURVA de loop: grado 1, un CV por vertice del edge
        # del parpado, creada una sola vez desde la seleccion con
        # build_loop_curve_from_selection. De ella salen tanto la linea del
        # parpado (rebuild a 7 CVs) como los joints de loop.
        #
        # *_loop_curve a None NO significa "no uses curva": significa "buscala
        # por convencion de nombre" (loop_curve_name). Solo hay que pasar un
        # nombre a mano si la curva se llama de otra forma.
        self.upper_loop_curve = upper_loop_curve
        self.lower_loop_curve = lower_loop_curve

        # --- Compatibilidad con la UI antigua ---
        # Los contadores y los sets de vertices ya no se usan. Se siguen
        # aceptando para que una llamada vieja no reviente, pero avisan: si
        # alguien los pasa esperando que hagan algo, tiene que enterarse.
        if upper_loop_count is not None or lower_loop_count is not None:
            cmds.warning("[EyesModule] upper_loop_count / lower_loop_count ya no "
                         "se usan: el numero de joints lo decide la curva de loop.")
        if upper_loop_set is not None or lower_loop_set is not None:
            cmds.warning("[EyesModule] upper_loop_set / lower_loop_set ya no se "
                         "usan: han sido sustituidos por upper_loop_curve / "
                         "lower_loop_curve.")

        # Los joints de loop son solo marcadores de posicion: no llevan ninguna
        # conexion. De ellos sale, en el paso siguiente, la cadena de aim que si
        # queda conectada, y de esa cadena saldran los joints de skinning.
        self.loop_positions = {"upper": [], "lower": []}
        self.loop_joints = {"upper": [], "lower": []}
        self.loop_joints_group = None

        self.loop_aim_joints = {"upper": [], "lower": []}
        self.loop_aim_ends = {"upper": [], "lower": []}
        self.loop_locators = {"upper": [], "lower": []}
        self.loop_point_infos = {"upper": [], "lower": []}
        self.loop_aim_matrices = {"upper": [], "lower": []}
        self.loop_distances = {"upper": [], "lower": []}
        self.loop_remaps = {"upper": [], "lower": []}
        self.loop_aim_group = None

        # Grupos del modulo
        self.rig_module_group = None
        self.settings_group = None

    # ------------------------------------------------------------------
    # SETUP LOCAL (mismo helper que el modulo de la boca)
    # ------------------------------------------------------------------
    def _build_off_network(self, prefix, base_name, source_ctrl, source_ctrl_grp, parent_group=None):
        """
        Crea el space-tracking local de un control.
        Si se pasa parent_group, el OFF se crea colgando de ese nodo (asi el setup
        local replica la misma jerarquia que tienen los controles).
        Devuelve (local_off, local_trn).
        """
        local_off, local_trn = self.group_maker.create_space_tracking_hierarchy(
            space_base_name=f"{prefix}_{base_name}Local",
            target_joint=source_ctrl_grp,
            parent_group=parent_group
        )

        mult_node = NodeCreator(
            side=prefix, node_type="multMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        decompose_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        decompose_trn_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()

        cmds.connectAttr(f"{source_ctrl}.matrix", f"{mult_node}.matrixIn[0]")
        cmds.connectAttr(f"{mult_node}.matrixSum", f"{decompose_node}.inputMatrix")

        translate_source = f"{decompose_node}.outputTranslate"
        if self.side == "R" and self.MIRROR_R_TRANSLATION:
            translate_source = self._build_translation_mirror(
                prefix, base_name, decompose_node)

        cmds.connectAttr(translate_source, f"{local_trn}.translate")
        cmds.connectAttr(f"{decompose_node}.outputRotate", f"{local_trn}.rotate")
        cmds.connectAttr(f"{decompose_node}.outputScale", f"{local_trn}.scale")
        cmds.connectAttr(f"{local_trn}.worldMatrix[0]", f"{decompose_trn_node}.inputMatrix")

        return local_off, local_trn

    def _build_translation_mirror(self, prefix, base_name, decompose_node):
        """
        Mete un multiplyDivide entre el decomposeMatrix y el _Local_TRN para
        invertir el signo de la traslacion en el lado R.

        Solo toca translate: la rotacion se queda como esta porque con
        orientaciones en mirror behaviour las rotaciones ya salen simetricas.
        Ver el comentario de MIRROR_R_TRANSLATION arriba de la clase.

        Devuelve el plug que hay que conectar al translate del TRN.
        """
        node_name = f"{prefix}_{base_name}LocalMirror_MDV"

        if not cmds.objExists(node_name):
            node_name = cmds.createNode("multiplyDivide", name=node_name)

        cmds.setAttr(f"{node_name}.operation", 1)  # 1 = multiplicar
        for index, axis in enumerate("XYZ"):
            cmds.setAttr(f"{node_name}.input2{axis}",
                         self.MIRROR_R_TRANSLATION_SIGN[index])

        cmds.connectAttr(f"{decompose_node}.outputTranslate",
                         f"{node_name}.input1", force=True)

        return f"{node_name}.output"

    def _mirror_control_axes(self):
        """
        Voltea los ejes de los grupos de control del lado R.

        Que se queda fuera y por que:

        - Los Sub. Cuelgan del control principal, asi que heredan el volteo.
          Si se les pusiera tambien, se cancelaria.
        - El eye_mid. Su joint va con un parentConstraint contra el control y
          su _GRP con un aimConstraint contra el eye_direct: meterle escala
          negativa se lo pasaria al joint del ojo. Ademas ese control se usa
          girando, y las rotaciones ya salen simetricas con orientaciones en
          mirror behaviour.

        Se llama despues del fleshy y ANTES de _constrain_in_between: los
        controles intermedios se colocan con un parentConstraint con mo=True
        contra sus vecinos, y ese offset tiene que medirse con los ejes ya
        volteados o los cuatro se desplazan hacia el centro del ojo.
        """
        if self.side != "R" or not self.MIRROR_R_CONTROL_AXES:
            return []

        targets = [ctrl_grp for guide, ctrl_grp in self.eye_control_groups.items()
                   if guide != self.eye_mid]

        if self.eye_direct_control_group:
            targets.append(self.eye_direct_control_group)

        flipped = []
        for group_node in targets:
            if not group_node or not cmds.objExists(group_node):
                continue

            for index, axis in enumerate("XYZ"):
                plug = f"{group_node}.scale{axis}"
                if cmds.getAttr(plug, lock=True) or cmds.listConnections(
                        plug, source=True, destination=False):
                    cmds.warning(f"[EyesModule] '{plug}' esta bloqueado o "
                                 f"conectado, no se voltea.")
                    continue
                cmds.setAttr(plug, self.MIRROR_R_CONTROL_SCALE[index])

            flipped.append(group_node)

        print(f"[EyesModule] Ejes volteados en {len(flipped)} grupos de control.")
        return flipped

    def _create_local_joint(self, local_trn):
        """
        Crea un joint por cada TRN del setup local, con el mismo nombre pero
        acabado en _JNT, y lo emparenta bajo su propio TRN (a cero).

        Se llama cuando toda la red de OFF/TRN ya esta construida, para que el
        joint quede siempre como hoja y ningun OFF acabe colgando de el.
        """
        if local_trn is None or not cmds.objExists(local_trn):
            cmds.warning(f"[EyesModule] No existe el TRN {local_trn}, no se crea su joint.")
            return None

        joint_name = local_trn.rsplit("_TRN", 1)[0] + "_JNT"
        if cmds.objExists(joint_name):
            return joint_name

        cmds.select(clear=True)
        local_joint = cmds.joint(n=joint_name)
        cmds.parent(local_joint, local_trn)

        # A cero para que quede exactamente sobre su TRN
        cmds.setAttr(f"{local_joint}.translate", 0, 0, 0)
        cmds.setAttr(f"{local_joint}.rotate", 0, 0, 0)
        cmds.setAttr(f"{local_joint}.jointOrient", 0, 0, 0)
        cmds.select(clear=True)

        return local_joint

    def _get_influence_joint(self, guide):
        """
        Devuelve el joint local que hay que usar como influencia de esa guia.
        Si la guia tiene Sub, se usa solo el joint del Sub (el del principal no se crea).
        """
        if guide in self.sub_control_guides:
            return self.eye_sub_local_joints.get(guide)

        return self.eye_local_joints.get(guide)

    def _get_driver_control(self, guide):
        """
        Control que conduce esa guia: el Sub si lo tiene (cuelga del principal,
        asi que ya arrastra su movimiento), y si no el principal.
        """
        if guide in self.sub_control_guides:
            return self.eye_sub_controls.get(guide)

        return self.eye_controls.get(guide)

    def _get_driver_local_trn(self, guide):
        """
        TRN del setup local que conduce esa guia: el del Sub si lo tiene,
        y si no el del principal.
        """
        if guide in self.sub_control_guides:
            return self.eye_sub_local_trns.get(guide)

        return self.eye_local_trns.get(guide)

    def _connect_follow_weights(self, constraint, follow_attribute, reverse_node):
        """
        Conecta los dos pesos de un parentConstraint al atributo de follow:
        - weightAliasList[0] (driver A, el parpado) directo desde el atributo.
        - weightAliasList[1] (driver B, la esquina) desde el reverse, para que
          los dos pesos sumen siempre 1.
        """
        weights = cmds.parentConstraint(constraint, q=True, weightAliasList=True)
        if not weights or len(weights) < 2:
            cmds.warning(f"[EyesModule] El constraint {constraint} no tiene dos pesos, no se conecta.")
            return

        cmds.connectAttr(follow_attribute, f"{constraint}.{weights[0]}", force=True)
        cmds.connectAttr(f"{reverse_node}.outputX", f"{constraint}.{weights[1]}", force=True)

    def _constrain_in_between(self):
        """
        Deja los controles intermedios (02 y 03) conducidos por sus dos vecinos:
        - El GRP del control intermedio va constrenido a los dos controles vecinos.
        - El OFF local del intermedio va constrenido a los dos TRN locales vecinos.

        El reparto de los dos pesos lo manda el atributo de follow del grupo de
        settings, con un reverse por intermedio que alimenta el segundo peso de
        los dos constraints (el del control y el del setup local).
        """
        if not self.settings_group or not cmds.objExists(self.settings_group):
            cmds.warning("[EyesModule] No existe el grupo de settings, no se conectan los follows.")
            return

        for guide, (driver_a_guide, driver_b_guide, attribute_name) in self.in_between_guides.items():
            follow_attribute = f"{self.settings_group}.{attribute_name}"

            # Un reverse por intermedio, compartido por los dos constraints
            reverse_name = f"{self.prefix}_{guide}Follow_REV"
            if cmds.objExists(reverse_name):
                cmds.delete(reverse_name)

            reverse_node = NodeCreator(
                side=self.prefix, node_type="reverse", base_name=guide,
                name="Follow", tag="CTRL", parent=None, custom_suffix=None
            ).create()
            reverse_node = cmds.rename(reverse_node, reverse_name)
            cmds.connectAttr(follow_attribute, f"{reverse_node}.inputX", force=True)

            # ---- Controles ----
            in_between_grp = self.eye_control_groups.get(guide)
            driver_a_ctrl = self._get_driver_control(driver_a_guide)
            driver_b_ctrl = self._get_driver_control(driver_b_guide)

            if in_between_grp and driver_a_ctrl and driver_b_ctrl and cmds.objExists(in_between_grp):
                # Borra un constraint previo por si se relanza la build
                old = cmds.listRelatives(in_between_grp, type="parentConstraint") or []
                if old:
                    cmds.delete(old)

                ctrl_constraint = cmds.parentConstraint(
                    driver_a_ctrl, driver_b_ctrl, in_between_grp, mo=True
                )[0]
                cmds.setAttr(f"{ctrl_constraint}.interpType", 2)  # 2 = Shortest
                self._connect_follow_weights(ctrl_constraint, follow_attribute, reverse_node)
            else:
                cmds.warning(f"[EyesModule] No se pudo constrenir el control intermedio {guide}.")

            # ---- Setup local: el OFF del intermedio sigue a los TRN vecinos ----
            in_between_off = self.eye_local_offs.get(guide)
            driver_a_trn = self._get_driver_local_trn(driver_a_guide)
            driver_b_trn = self._get_driver_local_trn(driver_b_guide)

            if in_between_off and driver_a_trn and driver_b_trn and cmds.objExists(in_between_off):
                old = cmds.listRelatives(in_between_off, type="parentConstraint") or []
                if old:
                    cmds.delete(old)

                local_constraint = cmds.parentConstraint(
                    driver_a_trn, driver_b_trn, in_between_off, mo=True
                )[0]
                cmds.setAttr(f"{local_constraint}.interpType", 2)  # 2 = Shortest
                self._connect_follow_weights(local_constraint, follow_attribute, reverse_node)
            else:
                cmds.warning(f"[EyesModule] No se pudo constrenir el OFF local intermedio {guide}.")

        cmds.select(clear=True)

    def _resolve_guide(self, guide):
        """
        Devuelve el nodo real de una guia, aceptandola con lado ('L_eye_mid')
        o sin el ('eye_mid'). Misma tolerancia que _build_eye_joints.
        """
        if cmds.objExists(guide):
            return guide
        if cmds.objExists(f"{self.side}_{guide}"):
            return f"{self.side}_{guide}"
        return None

    def _delete_local_setup(self, base_name):
        """
        Borra el setup local (_OFF con su _TRN y su _JNT dentro) de un control.

        Hace falta para el eye_mid: si viene de una build anterior en la que si
        lo tenia, esos nodos se quedarian sueltos sin conducir nada.
        """
        off_name = f"{self.prefix}_{base_name}Local_OFF"
        if cmds.objExists(off_name):
            cmds.delete(off_name)

    # ------------------------------------------------------------------
    # CADENA DE AIM DEL OJO
    # ------------------------------------------------------------------
    def _build_eye_mid_end_joint(self):
        """
        Crea el joint de la guia eye_mid_end y lo cuelga del joint de eye_mid.

        Va aparte de _build_eye_joints a proposito: los joints de ese metodo
        alimentan el bucle de controles y las curvas de los parpados, y este
        no lleva control propio ni entra en ninguna curva. Solo cierra la
        cadena para que el ojo tenga direccion.
        """
        mid_joint = self.eye_joints.get(self.eye_mid)
        if not mid_joint or not cmds.objExists(mid_joint):
            cmds.warning("[EyesModule] No existe el joint de eye_mid, no se crea la cadena.")
            return None

        guide_node = self._resolve_guide(self.eye_mid_end)
        if guide_node is None:
            cmds.warning(f"[EyesModule] No se encontro la guia {self.eye_mid_end}, "
                         "no se crea el joint final del ojo.")
            return None

        joint_name = f"{self.prefix}_{self.eye_mid_end}_JNT"
        if cmds.objExists(joint_name):
            cmds.delete(joint_name)

        cmds.select(clear=True)
        end_joint = cmds.joint(name=joint_name)
        cmds.matchTransform(end_joint, guide_node, position=True, rotation=True)

        # Emparentado DESPUES del match: cmds.parent conserva la posicion
        # mundial, asi que el joint se queda exactamente sobre su guia.
        cmds.parent(end_joint, mid_joint)
        cmds.select(clear=True)

        self.eye_mid_end_joint = end_joint

        return end_joint

    def _constrain_eye_mid_joint(self):
        """
        El control de eye_mid conduce a su joint con un parentConstraint.

        Este es el sustituto del setup local que llevaban los demas controles:
        el eye_mid no necesita la red de OFF/TRN porque su joint no skinea
        ninguna curva de parpado, solo tiene que seguir al control.
        """
        ctrl = self.eye_controls.get(self.eye_mid)
        joint = self.eye_joints.get(self.eye_mid)

        if not ctrl or not cmds.objExists(ctrl):
            cmds.warning("[EyesModule] No existe el control de eye_mid, no se constriñe su joint.")
            return None
        if not joint or not cmds.objExists(joint):
            cmds.warning("[EyesModule] No existe el joint de eye_mid, no se constriñe.")
            return None

        # Se rehace por si viene de una build anterior
        old = cmds.listRelatives(joint, children=True, type="parentConstraint") or []
        if old:
            cmds.delete(old)

        self.eye_mid_joint_constraint = cmds.parentConstraint(ctrl, joint, mo=True)[0]

        return self.eye_mid_joint_constraint

    def _build_eye_direct_control(self):
        """
        Control sobre la guia eye_direct, con su jerarquia de grupos.

        Sin joint: es el punto al que mira el ojo, no deforma nada.
        """
        guide_node = self._resolve_guide(self.eye_direct)
        if guide_node is None:
            cmds.warning(f"[EyesModule] No se encontro la guia {self.eye_direct}, "
                         "no se crea su control.")
            return None, None

        ctrl_name = f"{self.prefix}_{self.eye_direct}_CTRL"

        if not cmds.objExists(ctrl_name):
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["eyelid"],
                final_name=ctrl_name
            )
            ctrl_grp = self.group_maker.create_rig_hierarchy(
                ctrl, guide_node, match_rotation=True, world_space=True
            )
        else:
            ctrl = ctrl_name
            ctrl_grp = cmds.listRelatives(ctrl, parent=True)[0]

        self.eye_direct_control = ctrl
        self.eye_direct_control_group = ctrl_grp

        return ctrl, ctrl_grp

    def _aim_eye_mid_to_direct(self):
        """
        El _GRP del control de eye_mid apunta al control de eye_direct.

        Opciones del constraint, tal cual las de la ventana:
          - maintainOffset activado
          - aimVector (1, 0, 0)
          - upVector  (0, 1, 0)
          - worldUpType 'scene' (Scene up)
          - peso 1, sin ejes bloqueados

        Se constriñe el _GRP y no el control para dejarle al animador los
        canales del control libres por encima del aim.
        """
        mid_grp = self.eye_control_groups.get(self.eye_mid)
        direct_ctrl = self.eye_direct_control

        if not mid_grp or not cmds.objExists(mid_grp):
            cmds.warning("[EyesModule] No existe el _GRP del control de eye_mid, no se aplica el aim.")
            return None
        if not direct_ctrl or not cmds.objExists(direct_ctrl):
            cmds.warning("[EyesModule] No existe el control de eye_direct, no se aplica el aim.")
            return None

        old = cmds.listRelatives(mid_grp, children=True, type="aimConstraint") or []
        if old:
            cmds.delete(old)

        self.eye_mid_aim_constraint = cmds.aimConstraint(
            direct_ctrl, mid_grp,
            maintainOffset=True,
            aimVector=(1.0, 0.0, 0.0),
            upVector=(0.0, 1.0, 0.0),
            worldUpType="scene",
            weight=1.0
        )[0]

        return self.eye_mid_aim_constraint

    def _get_eyelid_guide_positions(self):
        """
        Posiciones de las 8 guias de parpado, muestreadas sobre las lineas.

        Antes cada una era un joint de guia colocado a mano en la escena. Ahora
        se sacan de la linea del parpado, que viene de la curva de loop, que
        viene del edge de la malla. Los NOMBRES de guia se conservan tal cual
        como identificadores, asi que todo lo que hay detras (controles,
        fleshy, blink, in-between, mirror) no se entera del cambio.

        Las dos comisuras las pone la linea superior: son el mismo punto en las
        dos y si las pusiera tambien la inferior se pisarian entre ellas.
        """
        positions = {}

        for upper in (True, False):
            curve = self.upper_curve if upper else self.lower_curve
            if not curve or not cmds.objExists(curve):
                continue

            parameter_range = self._get_curve_parameter_range(curve)
            if not parameter_range:
                continue

            minimum, maximum = parameter_range
            span = maximum - minimum

            ordered_guides = self._get_ordered_eyelid_guides(upper=upper)

            for guide, fraction in zip(ordered_guides, self.EYELID_GUIDE_FRACTIONS):
                if guide in positions:
                    continue
                parameter = minimum + span * fraction
                positions[guide] = cmds.pointOnCurve(curve, pr=parameter, position=True)

        return positions

    def _build_eye_joints(self):
        """
        Crea los joints del ojo.

        eye_mid sigue saliendo de su guia: es el globo ocular y no tiene nada
        que ver con el borde del parpado.

        Las 8 guias de parpado ya no necesitan joint de guia en la escena: su
        posicion se muestrea sobre la linea, que sale de la curva de loop. Por
        eso este metodo tiene que correr DESPUES de _build_eyelid_curves.

        La orientacion de los 8 la da el guia de eye_mid, no cada guia por su
        cuenta: sin guias no hay de donde sacar 8 orientaciones distintas, y
        compartir la del ojo es ademas lo que hace que los controles del
        parpado tengan todos los mismos ejes.
        """
        guides = [
            self.eye_mid,
            self.eye_inner_corner,
            self.eye_outer_corner,
            self.eyelid_up,
            self.eyelid_low,
            self.eyelid_up02,
            self.eyelid_up03,
            self.eyelid_low02,
            self.eyelid_low03,
        ]

        # Limpieza de una build anterior para poder relanzar el script
        self.joints_group = f"{self.prefix}_eyeJoints_GRP"
        if cmds.objExists(self.joints_group):
            cmds.delete(self.joints_group)

        self.eye_joints = {}
        created_joints = []

        guide_positions = self._get_eyelid_guide_positions()
        orientation_source = self._resolve_guide(self.eye_mid)

        for guide in guides:
            joint_name = f"{self.prefix}_{guide}_JNT"
            if cmds.objExists(joint_name):
                cmds.delete(joint_name)

            # El eye_mid es el unico que sigue necesitando su guia en la escena
            if guide == self.eye_mid:
                guide_node = self._resolve_guide(guide)
                if guide_node is None:
                    cmds.warning(f"[EyesModule] No se encontro la guia {guide}, "
                                 f"se omite su joint.")
                    continue

                cmds.select(clear=True)
                new_joint = cmds.joint(name=joint_name)
                cmds.matchTransform(new_joint, guide_node, position=True, rotation=True)

                self.eye_joints[guide] = new_joint
                created_joints.append(new_joint)
                continue

            position = guide_positions.get(guide)
            if position is None:
                cmds.warning(f"[EyesModule] No hay posicion sobre la linea para "
                             f"{guide}, se omite su joint.")
                continue

            cmds.select(clear=True)
            new_joint = cmds.joint(name=joint_name)
            cmds.xform(new_joint, worldSpace=True, translation=position)

            if orientation_source:
                cmds.matchTransform(new_joint, orientation_source,
                                    position=False, rotation=True)

            self.eye_joints[guide] = new_joint
            created_joints.append(new_joint)

        if not created_joints:
            cmds.warning("[EyesModule] No se creo ningun joint del ojo.")
            self.joints_group = None
            return None

        self.joints_group = cmds.group(created_joints, name=self.joints_group)
        cmds.select(clear=True)

        return self.joints_group

    def _get_ordered_eyelid_guides(self, upper=True):
        """
        Devuelve las guias del parpado ordenadas de esquina interna a esquina externa.
        Son las 5 que tienen joint propio; la curva ademas lleva 2 CVs intermedios
        entre cada esquina y su secundario contiguo.
        """
        if upper:
            return [
                self.eye_inner_corner,
                self.eyelid_up02,
                self.eyelid_up,
                self.eyelid_up03,
                self.eye_outer_corner,
            ]

        return [
            self.eye_inner_corner,
            self.eyelid_low02,
            self.eyelid_low,
            self.eyelid_low03,
            self.eye_outer_corner,
        ]

    def _get_ordered_eyelid_joints(self, upper=True):
        """
        Devuelve la lista de joints de guia del parpado ordenados de esquina interna
        a esquina externa. Son 5 joints.
        """
        return [f"{self.prefix}_{guide}_JNT" for guide in self._get_ordered_eyelid_guides(upper=upper)]

    def _build_eyelid_line_curve(self, upper=True):
        """
        Construye la linea de un parpado a partir de su curva de loop.

        La linea es un duplicado de la curva cruda rebuildeado a grado 3 con 4
        spans, o sea 7 CVs. Ese numero no es negociable: CV_WEIGHTS reparte los
        pesos por indice de CV y esta escrito para 7.

        El rebuild es tambien el que convierte "una poligonal con un CV por
        vertice" en "una curva suave que se puede deformar con 5 joints", que es
        exactamente lo que el profe pedia: primero la curva desde la malla, y
        encima de ella todo lo demas.
        """
        loop_curve = self._resolve_loop_curve(upper=upper)
        if not loop_curve:
            label = "superior" if upper else "inferior"
            cmds.warning(f"[EyesModule] No hay curva de loop para el parpado "
                         f"{label}. Selecciona el edge en la malla y lanza "
                         f"build_loop_curve_from_selection antes de construir.")
            return None

        curve_name = self.line_curve_name(self.side, self.rig_name, upper=upper)
        if cmds.objExists(curve_name):
            cmds.delete(curve_name)

        curve_transform = cmds.duplicate(loop_curve, name=curve_name)[0]

        # Por si la curva de loop estaba dentro de algun grupo: la linea vive en
        # el mundo hasta que _organize_outliner la coloque.
        if cmds.listRelatives(curve_transform, parent=True):
            curve_transform = cmds.parent(curve_transform, world=True)[0]

        cmds.rebuildCurve(
            curve_transform, ch=0, rpo=1, rt=0, end=1, kr=0, kcp=0, kep=1, kt=0,
            s=self.LINE_CURVE_SPANS, d=self.LINE_CURVE_DEGREE, tol=0.01
        )
        cmds.setAttr(f"{curve_transform}.lineWidth", 3)

        cv_count = self._curve_cv_count(curve_transform)
        if cv_count != len(self.CV_WEIGHTS):
            cmds.warning(f"[EyesModule] {curve_name} ha salido con {cv_count} CVs y "
                         f"CV_WEIGHTS tiene {len(self.CV_WEIGHTS)} entradas. El "
                         f"skinning de la curva va a quedar incompleto.")

        return curve_transform

    def _build_eyelid_curves(self):
        """
        Construye las dos lineas de parpado desde sus curvas de loop.

        Esto ya no depende de los joints de guia: es al reves, son los joints
        los que salen de estas lineas. Por eso en build() va antes que
        _build_eye_joints.
        """
        self.upper_curve = self._build_eyelid_line_curve(upper=True)
        self.lower_curve = self._build_eyelid_line_curve(upper=False)

        cmds.select(clear=True)

        return self.upper_curve, self.lower_curve

    def _skin_eyelid_curve(self, curve_transform, upper=True):
        """
        Skinea la curva del parpado a sus joints locales y aplica los pesos
        fijos de CV_WEIGHTS (los mismos para la curva de arriba y la de abajo).

        maximumInfluences=2 y obeyMaxInfluences desactivado, porque los CVs
        intermedios se reparten entre dos joints.
        """
        if curve_transform is None or not cmds.objExists(curve_transform):
            return None

        ordered_guides = self._get_ordered_eyelid_guides(upper=upper)
        influence_joints = [self._get_influence_joint(guide) for guide in ordered_guides]

        missing = [g for g, j in zip(ordered_guides, influence_joints) if not j or not cmds.objExists(j)]
        if missing:
            cmds.warning(f"[EyesModule] Faltan joints locales {missing}, no se skinea {curve_transform}.")
            return None

        # Borra un skinCluster previo por si se relanza la build
        old_skins = cmds.ls(cmds.listHistory(curve_transform) or [], type="skinCluster")
        if old_skins:
            cmds.delete(old_skins)

        skin_name = curve_transform.rsplit("_CRV", 1)[0] + "_SKN"
        skin_cluster = cmds.skinCluster(
            influence_joints, curve_transform,
            toSelectedBones=True, bindMethod=0, skinMethod=0,
            maximumInfluences=2, obeyMaxInfluences=False, dropoffRate=4,
            n=skin_name
        )[0]

        # Permite pesos repartidos entre varias influencias al aplicar CV_WEIGHTS
        cmds.setAttr(f"{skin_cluster}.maintainMaxInfluences", 0)

        curve_shape = cmds.listRelatives(curve_transform, shapes=True)[0]
        cv_count = cmds.getAttr(f"{curve_shape}.spans") + cmds.getAttr(f"{curve_shape}.degree")

        for index in range(cv_count):
            weights = self.CV_WEIGHTS.get(index)
            if weights is None:
                cmds.warning(f"[EyesModule] No hay pesos definidos para el cv[{index}] de {curve_transform}.")
                continue

            transform_values = [
                (influence_joint, weight)
                for influence_joint, weight in zip(influence_joints, weights)
                if weight > 0.0
            ]

            cmds.skinPercent(
                skin_cluster, f"{curve_transform}.cv[{index}]",
                transformValue=transform_values
            )

        cmds.select(clear=True)

        return skin_cluster

    def _clean_old_blink_attributes(self):
        """
        Quita el separador y los atributos de blink de los controles de
        eyelid_up / eyelid_low, donde se creaban en builds anteriores.
        Solo borra los atributos de BLINK_ATTRIBUTES y el separador: nada mas.
        """
        host = self._get_attribute_host()

        old_controls = [
            self.eye_controls.get(self.eyelid_up),
            self.eye_controls.get(self.eyelid_low),
            self.eye_controls.get(self.eye_mid),   # vivian aqui hasta ahora
        ]
        old_controls = [c for c in old_controls if c and c != host]

        attr_names = (["extraAttrSep"]
                      + [entry[0] for entry in self.BLINK_ATTRIBUTES]
                      + [setup["attribute"] for setup in self.fleshy_setups])

        for old_ctrl in old_controls:
            if not old_ctrl or not cmds.objExists(old_ctrl):
                continue

            for attr_name in attr_names:
                if not cmds.attributeQuery(attr_name, node=old_ctrl, exists=True):
                    continue

                cmds.setAttr(f"{old_ctrl}.{attr_name}", lock=False)
                cmds.deleteAttr(f"{old_ctrl}.{attr_name}")

    def _offset_eye_mid_shape(self):
        """
        Lleva la shape del control de eye_mid hasta la posicion del joint de
        eye_mid_end. Se mueven solo los CV de la curva en world space, asi que
        el transform y su pivote se quedan exactamente donde estaban.

        Idempotente: deja un atributo marca en el control para no volver a
        aplicar el offset si se relanza la build sobre la misma escena (el
        control sobrevive entre builds y se desplazaria dos veces).
        """
        ctrl = self.eye_controls.get(self.eye_mid)
        if not ctrl or not cmds.objExists(ctrl):
            cmds.warning("[EyesModule] No existe el control de eye_mid, no se mueve la shape.")
            return None

        end_joint = self.eye_mid_end_joint
        if not end_joint or not cmds.objExists(end_joint):
            cmds.warning("[EyesModule] No existe el joint de eye_mid_end, no se mueve la shape.")
            return None

        if cmds.attributeQuery("shapeOffsetToEnd", node=ctrl, exists=True):
            return ctrl

        shapes = cmds.listRelatives(ctrl, shapes=True, type="nurbsCurve", fullPath=True) or []
        if not shapes:
            cmds.warning(f"[EyesModule] {ctrl} no tiene shapes de curva, no se mueve nada.")
            return None

        # Referencia: el pivote del control, que es justo lo que no se toca.
        ctrl_position = cmds.xform(ctrl, q=True, ws=True, rp=True)
        end_position = cmds.xform(end_joint, q=True, ws=True, t=True)
        offset = [end_position[i] - ctrl_position[i] for i in range(3)]

        for shape in shapes:
            cmds.move(offset[0], offset[1], offset[2], f"{shape}.cv[*]",
                      relative=True, worldSpace=True)

        cmds.addAttr(ctrl, ln="shapeOffsetToEnd", at="bool", dv=True, k=False)
        cmds.setAttr(f"{ctrl}.shapeOffsetToEnd", lock=True)

        return ctrl

    def _get_attribute_host(self):
        """
        Control donde viven los atributos de blink y de fleshy: el de eye_mid.

        El documento los pone en el eyeDirect y se llego a hacer asi, pero en
        esta cara el eye_mid es el control que se usa para el parpadeo, asi que
        se quedan aqui. Si algun dia se quiere seguir el documento al pie de la
        letra, es cambiar este metodo por self.eye_direct_control y mover la
        llamada a _add_blink_attributes despues de _build_eye_direct_control en
        el build.
        """
        return self.eye_controls.get(self.eye_mid)

    def _add_blink_attributes(self):
        """
        Anade al control de eye_mid el separador de atributos extra y los tres
        floats de blink.

        Idempotente: si el atributo ya existe en el control no se vuelve a crear,
        asi que se puede relanzar la build sin que reviente.
        """
        ctrl = self._get_attribute_host()
        if not ctrl or not cmds.objExists(ctrl):
            cmds.warning("[EyesModule] No hay control donde poner los atributos "
                         "de blink.")
            return None

        # Los atributos vivian en los parpados: se limpian de ahi antes de nada.
        self._clean_old_blink_attributes()

        if not cmds.attributeQuery("extraAttrSep", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="extraAttrSep", nn="EXTRA_ATTR",
                         at="enum", en="------", k=False)

        # Con k=False el enum existe pero no se ve: hay que marcarlo en el
        # Channel Box y bloquearlo para que se pinte como separador.
        cmds.setAttr(f"{ctrl}.extraAttrSep", channelBox=True, lock=True)

        for long_name, nice_name, default_value, min_value, max_value in self.BLINK_ATTRIBUTES:
            if cmds.attributeQuery(long_name, node=ctrl, exists=True):
                continue

            cmds.addAttr(
                ctrl, ln=long_name, nn=nice_name,
                at="float", min=min_value, max=max_value,
                dv=default_value, k=True
            )

        return ctrl

    def _add_fleshy_attribute(self, setup):
        """
        Anade al control de eye_mid el float de un setup de fleshy.

        A 0 esos controles no se enteran de por donde mira el ojo; a 1 le siguen
        todo lo que permita su multiplicador. El defecto es 0, asi que montar el
        sistema no cambia nada hasta que alguien lo sube a mano.
        """
        ctrl = self._get_attribute_host()
        if not ctrl or not cmds.objExists(ctrl):
            cmds.warning("[EyesModule] No hay control donde poner los atributos "
                         "de fleshy.")
            return None

        long_name = setup["attribute"]

        if not cmds.attributeQuery(long_name, node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln=long_name, nn=setup["nice_name"],
                         at="float", min=0, max=1,
                         dv=self.FLESHY_DEFAULT, k=True)

        return f"{ctrl}.{long_name}"

    def _build_fleshy_delta(self, joint):
        """
        Devuelve el decomposeMatrix que da cuanto ha girado el ojo DESDE SU
        REPOSO, expresado en el marco de ese reposo.

            eye_mid_JNT.worldMatrix[0] -> MMX.matrixIn[0]
            <inversa del reposo>          MMX.matrixIn[1]
            MMX.matrixSum              -> DCM.inputMatrix

        Por que hace falta esto y no vale leer joint.rotateY directamente:
        _build_eye_joints coloca los joints con matchTransform, que escribe la
        orientacion en rotate y deja jointOrient a cero. O sea que joint.rotate
        en reposo NO es cero, lleva la orientacion de fabrica del ojo.

        En la L eso pasa medio desapercibido porque el ojo mira casi de frente y
        el reposo son unos pocos grados. En la R el ojo mira al otro lado y el
        reposo esta cerca de +-180: al meter esa rotacion absoluta en el grupo,
        el parpado entero se da la vuelta. De ahi las vueltas de la curva.

        Con la delta, el valor que entra vale cero en reposo en los dos lados y
        se queda siempre en angulos pequenos, lejos del salto de +-180 donde el
        Euler se vuelve loco. Y el multiplicador pasa a escalar algo que
        significa lo que dice: los grados que el ojo ha girado.

        La red es una sola para los dos setups: la delta es la misma, lo unico
        que cambia entre parpados y esquinas es cuanto se le hace caso.
        """
        multiply_name = f"{self.prefix}_eyeFleshyDelta_MMX"
        decompose_name = f"{self.prefix}_eyeFleshyDelta_DCM"

        for node_name in (multiply_name, decompose_name):
            if cmds.objExists(node_name):
                cmds.delete(node_name)

        multiply = cmds.createNode("multMatrix", n=multiply_name)
        cmds.connectAttr(f"{joint}.worldMatrix[0]", f"{multiply}.matrixIn[0]")

        # Inversa del reposo, congelada como valor: el aim del ojo ya esta
        # montado y el direct en su sitio, asi que esta es la pose de partida.
        rest_inverse = cmds.getAttr(f"{joint}.worldInverseMatrix[0]")
        cmds.setAttr(f"{multiply}.matrixIn[1]", *rest_inverse, type="matrix")

        decompose = cmds.createNode("decomposeMatrix", n=decompose_name)
        cmds.connectAttr(f"{multiply}.matrixSum", f"{decompose}.inputMatrix")

        return decompose

    def _build_fleshy_blend(self, setup, driver_attribute, delta):
        """
        Red que mezcla entre 'quieto' y 'lo que ha girado el ojo'.

            ctrl.<atributo>   -> MDL.input1
            <multiplicador>      MDL.input2
            MDL.output        -> BLC.blender
            DCM.outputRotateY -> BLC.color1G
            DCM.outputRotateZ -> BLC.color1B

        El DCM es la delta de _build_fleshy_delta, no los canales del joint: en
        reposo vale cero en los dos lados, asi que color2 si puede ir a ceros y
        la mezcla es directamente 'cuanto de lo girado se le pasa al parpado'.

        Solo entran Y y Z porque son los dos ejes por los que mira el ojo:
        arriba-abajo y lado a lado. El giro sobre su propio eje no tiene que
        arrastrar el parpado.

        El multiplicador va en el blender y no en la salida por comodidad: el
        atributo sigue yendo de 0 a 1 en el channel box y lo que se atenua es la
        cantidad de delta que llega.
        """
        base_name = f"{self.prefix}_{setup['name']}"

        for node_name in (f"{base_name}_MDL", f"{base_name}_BLC"):
            if cmds.objExists(node_name):
                cmds.delete(node_name)

        # Atenuador: se toca en input2 sin recablear nada.
        multiplier = cmds.createNode("multDoubleLinear", n=f"{base_name}_MDL")
        cmds.connectAttr(driver_attribute, f"{multiplier}.input1")
        cmds.setAttr(f"{multiplier}.input2", setup["multiplier"])

        blend = cmds.createNode("blendColors", n=f"{base_name}_BLC")
        cmds.connectAttr(f"{multiplier}.output", f"{blend}.blender")

        cmds.connectAttr(f"{delta}.outputRotateX", f"{blend}.color1R")
        cmds.connectAttr(f"{delta}.outputRotateY", f"{blend}.color1G")

        # El eje X no lo conduce nadie y los defaults del nodo no son cero
        # cmds.setAttr(f"{blend}.color1R", 0)
        # for channel in "RGB":
        #     cmds.setAttr(f"{blend}.color2{channel}", 0)

        return blend, multiplier

    def _build_fleshy_groups(self, base_name, joint):
        """
        Crea la pareja de grupos de un setup de fleshy: uno quieto en el centro
        del ojo y su duplicado colgando de el.

        El de dentro se hace duplicando al de fuera y no creando otro y
        matcheandolo: al duplicar y emparentar, el hijo queda con los canales a
        cero limpios.

        El match es de posicion Y rotacion. La delta que va a entrar en el rotate
        esta medida en el marco del reposo del ojo, asi que el grupo tiene que
        estar orientado igual que ese reposo para que los ejes signifiquen lo
        mismo a los dos lados de la conexion.

        El pivote si esta en el centro del ojo, que es lo que hace que lo que
        cuelgue orbite alrededor del globo ocular en vez de girar sobre si mismo.
        """
        off_name = f"{base_name}_OFF"
        trn_name = f"{base_name}_TRN"

        # Al reconstruir hay que sacar lo que hubiera dentro antes de borrar,
        # o se irian por delante las jerarquias de controles.
        for node in (trn_name, off_name):
            if not cmds.objExists(node):
                continue
            children = cmds.listRelatives(node, children=True, fullPath=True) or []
            if children:
                cmds.parent(children, world=True)
            cmds.delete(node)

        off_group = cmds.group(em=True, n=off_name)
        cmds.matchTransform(off_group, joint, position=True, rotation=True)

        trn_group = cmds.duplicate(off_group, n=trn_name)[0]
        cmds.parent(trn_group, off_group)

        return off_group, trn_group

    def _connect_fleshy_rotation(self, blend, trn_group):
        """
        Mete la salida del blendColors en la rotacion del grupo.

        Canal a canal en vez de compound: el rotate lleva unidades de angulo y el
        blendColors no, asi Maya mete su unitConversion en cada canal y no hay
        sorpresas con la conversion del compuesto entero.
        """
        for channel, axis in (("R", "X"), ("G", "Y"), ("B", "Z")):
            if axis == self.FLESHY_SKIP_AXIS:
                # El twist del ojo se queda fuera a proposito, ver
                # FLESHY_SKIP_AXIS. Solo se conectan DOS ejes.
                continue

            cmds.connectAttr(f"{blend}.output{channel}",
                             f"{trn_group}.rotate{axis}", force=True)

        return trn_group

    def _build_fleshy_chain(self, blend, base_name, joint, targets):
        """
        Grupos + conexion + emparentado de una rama del fleshy.

        El orden importa: primero se conecta la rotacion y solo despues se
        cuelgan los targets. En reposo la delta es cero, asi que el grupo esta a
        ceros cuando cmds.parent calcula los offsets locales y nada salta de
        sitio al montarlo.
        """
        groups = self._build_fleshy_groups(base_name, joint)
        if not groups:
            return None

        off_group, trn_group = groups
        self._connect_fleshy_rotation(blend, trn_group)

        for node in targets:
            if not node or not cmds.objExists(node):
                continue
            cmds.parent(node, trn_group)

        return off_group, trn_group

    def _build_fleshy_setup(self):
        """
        Monta los setups de fleshy: uno para los parpados y otro, aparte y con su
        propio atributo y su propio atenuador, para las esquinas.

        Van separados porque las esquinas estan mucho mas ancladas
        anatomicamente que el centro del parpado: con el mismo valor se pasan de
        largo. Cada uno tiene su cadena entera (atributo, blendColors, grupos),
        asi que se regulan por separado sin tocarse.

        Cada setup se duplica ademas en el lado local. Hace falta porque el setup
        local lee ctrl.matrix, o sea la matriz LOCAL del control respecto a su
        propio ANIM: solo se entera de lo que el animador mueve el control, no de
        donde este colgado su GRP. Sin esa parte, subir el atributo inclinaria los
        controles en pantalla pero los joints no se moverian. Se apaga con
        FLESHY_DRIVE_LOCAL.

        Va despues de los controles (necesita sus GRP y sus OFF locales) y antes
        de _constrain_in_between y _group_rig_module, para que los constraints y
        la agrupacion se hagan con la jerarquia ya en su sitio final.
        """
        joint = self.eye_joints.get(self.eye_mid)
        if not joint or not cmds.objExists(joint):
            return None

        self.fleshy_nodes = {}

        # Una sola delta para los dos setups
        delta = self._build_fleshy_delta(joint)

        for setup in self.fleshy_setups:
            driver_attribute = self._add_fleshy_attribute(setup)
            if not driver_attribute:
                continue

            built = self._build_fleshy_blend(setup, driver_attribute, delta)
            if not built:
                continue

            blend, multiplier = built
            base_name = f"{self.prefix}_{setup['name']}"

            data = {"blend": blend, "multiplier": multiplier,
                    "attribute": driver_attribute, "local_off": None}

            control_groups = [self.eye_control_groups.get(guide)
                              for guide in setup["guides"]]
            control_chain = self._build_fleshy_chain(
                blend, base_name, joint, control_groups)
            if control_chain:
                data["off"], data["trn"] = control_chain

            if self.FLESHY_DRIVE_LOCAL:
                local_offs = [self.eye_local_offs.get(guide)
                              for guide in setup["guides"]]
                local_chain = self._build_fleshy_chain(
                    blend, f"{base_name}Local", joint, local_offs)
                if local_chain:
                    data["local_off"], data["local_trn"] = local_chain

            self.fleshy_nodes[setup["key"]] = data

        cmds.select(clear=True)

        return self.fleshy_nodes

    def _build_settings_group(self):
        """
        Crea el grupo de settings del modulo, con los atributos de follow de los
        parpados. Transformaciones bloqueadas y ocultas: solo sirve de contenedor
        de atributos, no se anima ni se mueve.

        Se llama antes de los constraints, porque sus atributos son los que
        conducen los pesos.
        """
        settings_name = f"{self.prefix}_eyeLidRigSettings_GRP"

        if cmds.objExists(settings_name):
            cmds.delete(settings_name)

        settings_group = cmds.group(em=True, n=settings_name)

        for long_name, nice_name, default_value in self.SETTINGS_ATTRIBUTES:
            cmds.addAttr(
                settings_group, ln=long_name, nn=nice_name,
                at="float", min=0, max=1, dv=default_value, k=True
            )

        # Bloquea y oculta translate / rotate / scale y la visibilidad
        for attr in ["translateX", "translateY", "translateZ",
                     "rotateX", "rotateY", "rotateZ",
                     "scaleX", "scaleY", "scaleZ", "visibility"]:
            cmds.setAttr(f"{settings_group}.{attr}", lock=True, keyable=False, channelBox=False)

        return settings_group

    # ------------------------------------------------------------------
    # SISTEMA DE BLINK
    # ------------------------------------------------------------------
    def _duplicate_eyelid_curve(self, source_curve, name):
        """
        Duplica una curva de parpado y la deja suelta en la raiz de la escena.

        cmds.duplicate copia la forma actual sin arrastrar el skinCluster, que
        es justo lo que hace falta para un target de blendShape.

        Lo que si arrastra es la shape intermedia (la Orig del skinCluster de la
        linea de origen), que llega muerta y con el nombre de la copia. Se borra
        aqui: si no, luego hay dos shapes con nombre parecido colgando de la
        misma curva y tanto getAttr como el que busca la Orig del blendShape se
        lian.
        """
        if cmds.objExists(name):
            cmds.delete(name)

        duplicated = cmds.duplicate(source_curve, n=name)[0]

        if cmds.listRelatives(duplicated, parent=True):
            cmds.parent(duplicated, world=True)

        leftovers = [
            shape
            for shape in cmds.listRelatives(duplicated, shapes=True, fullPath=True) or []
            if cmds.getAttr(f"{shape}.intermediateObject")
        ]
        if leftovers:
            cmds.delete(leftovers)

        return duplicated

    def _build_blink_curves(self):
        """
        Crea las cinco curvas del sistema de blink a partir de las dos lineas
        de parpado ya construidas y skinneadas.

        Las dos NegateBlink nacen como copias exactas de su original: son la
        pose de apertura y hay que esculpirlas a mano. Mientras no se toquen,
        su peso no cambia nada.
        """
        upper, lower = self.upper_curve, self.lower_curve

        if not upper or not cmds.objExists(upper) or not lower or not cmds.objExists(lower):
            cmds.warning("[EyesModule] Faltan las lineas de parpado, no se crea el blink.")
            return None

        self.blink_height_curve = self._duplicate_eyelid_curve(
            lower, f"{self.prefix}_eyelidBlinkHeight_CRV")
        self.upper_blinked_curve = self._duplicate_eyelid_curve(
            upper, f"{self.prefix}_eyelidUpperBlinked_CRV")
        self.lower_blinked_curve = self._duplicate_eyelid_curve(
            lower, f"{self.prefix}_eyelidLowerBlinked_CRV")
        self.upper_negate_curve = self._duplicate_eyelid_curve(
            upper, f"{self.prefix}_eyelidUpperNegateBlink_CRV")
        self.lower_negate_curve = self._duplicate_eyelid_curve(
            lower, f"{self.prefix}_eyelidLowerNegateBlink_CRV")

        return [self.blink_height_curve,
                self.upper_blinked_curve, self.lower_blinked_curve,
                self.upper_negate_curve, self.lower_negate_curve]

    def _get_deformed_shape(self, transform):
        """
        Shape visible (la que no es intermediateObject) de un transform.

        Devuelve el nombre largo: con nombre corto, si en la escena hay otro
        nodo que se llame igual, cmds.getAttr devuelve una lista con el valor de
        todos los que coinciden en vez de un unico valor.
        """
        if not transform or not cmds.objExists(transform):
            return None

        shapes = cmds.listRelatives(
            transform, shapes=True, noIntermediate=True, fullPath=True) or []

        return shapes[0] if shapes else None

    def _get_original_shape(self, transform):
        """
        Shape Orig (intermediateObject) que alimenta a los deformadores del
        transform. Solo existe si la curva ya tiene un deformador encima, asi
        que esto se llama despues de crear los blendShape.
        """
        shape = self._get_deformed_shape(transform)
        if not shape:
            return None

        plugs = cmds.deformableShape(shape, originalGeometry=True) or []
        if plugs and plugs[0]:
            return plugs[0].split(".")[0]

        # Por si deformableShape no devuelve nada: primer intermediate del transform
        for candidate in cmds.listRelatives(transform, shapes=True, fullPath=True) or []:
            if cmds.getAttr(f"{candidate}.intermediateObject"):
                return candidate

        return None

    def _connect_live_blink_bases(self):
        """
        Conecta el worldSpace de las lineas de parpado skinneadas al .create de
        la Orig de cada curva del blink.

            eyelidLowerLine -> BlinkHeight_CRVShapeOrig.create
            eyelidUpperLine -> UpperBlinked_CRVShapeOrig.create
            eyelidLowerLine -> LowerBlinked_CRVShapeOrig.create

        Sin estas conexiones la base de cada blendShape es la copia congelada
        del momento de la build: al mover un control la linea original se
        deforma pero las curvas del blink se quedan clavadas donde estaban.
        Con la conexion la base es la propia linea deformada, asi que todas las
        curvas siguen a los controles y el blink se aplica encima: las Blinked
        cierran hacia donde este la BlinkHeight en ese momento, no hacia una
        posicion fija.

        La cadena queda encadenada sola: la BlinkHeight tiene base viva y su
        propia salida es target de las dos Blinked, que tambien tienen base
        viva.
        """
        pairs = [
            (self.lower_curve, self.blink_height_curve),
            (self.upper_curve, self.upper_blinked_curve),
            (self.lower_curve, self.lower_blinked_curve),
        ]

        connected = []

        for source_curve, target_curve in pairs:
            source_shape = self._get_deformed_shape(source_curve)
            orig_shape = self._get_original_shape(target_curve)

            if not source_shape or not orig_shape:
                cmds.warning(
                    f"[EyesModule] No se puede conectar la base viva de {target_curve}.")
                continue

            cmds.connectAttr(f"{source_shape}.worldSpace[0]",
                             f"{orig_shape}.create", force=True)
            connected.append(orig_shape)

        return connected

    def _offset_negate_curves(self, factor=None):
        """
        Separa las dos curvas NegateBlink de su original empujando sus CVs hacia
        fuera del centro del ojo, para que su arco quede mas largo que el del
        resto de curvas.

        Son los targets de apertura: al abrir mas el ojo el parpado se aleja del
        globo ocular y su arco se alarga, pero las dos esquinas se quedan
        clavadas. Por eso cv[0] y el ultimo no se tocan y el empuje lleva un
        falloff que es maximo en el centro del parpado.

        Recien duplicadas son copias exactas de su original y su peso no hace
        nada. Esto deja una pose de apertura de partida ya utilizable, que sigue
        siendo esculpible CV a CV despues.
        """
        factor = self.NEGATE_OFFSET if factor is None else factor

        if not factor:
            return []

        center_joint = f"{self.prefix}_{self.eye_mid}_JNT"
        if not cmds.objExists(center_joint):
            cmds.warning("[EyesModule] Sin joint de eye_mid no se offsetean las NegateBlink.")
            return None

        center = cmds.xform(center_joint, q=True, ws=True, t=True)

        offset_curves = []

        for curve in (self.upper_negate_curve, self.lower_negate_curve):
            if not curve or not cmds.objExists(curve):
                continue

            shape = self._get_deformed_shape(curve)
            if not shape:
                cmds.warning(f"[EyesModule] {curve} no tiene shape, no se offsetea.")
                continue

            # Los CVs se cuentan listandolos, no con spans + degree: asi no
            # depende de que getAttr resuelva bien el nombre de la shape.
            cvs = cmds.ls(f"{shape}.cv[*]", flatten=True) or []
            cv_count = len(cvs)
            if cv_count < 3:
                continue

            last_index = cv_count - 1

            positions = [cmds.pointPosition(cv, world=True) for cv in cvs]

            # Radio de referencia: distancia media de la curva al centro del ojo,
            # para que el offset escale con el tamano del personaje.
            distances = [
                math.sqrt(sum((p - c) ** 2 for p, c in zip(position, center)))
                for position in positions
            ]
            radius = sum(distances) / len(distances)

            for index in range(1, last_index):
                position = positions[index]

                direction = [p - c for p, c in zip(position, center)]
                length = math.sqrt(sum(v ** 2 for v in direction))
                if length < 1e-6:
                    continue
                direction = [v / length for v in direction]

                # 0 en las esquinas, 1 en el centro del parpado
                falloff = math.sin(math.pi * index / float(last_index))
                amount = radius * factor * falloff

                cmds.xform(
                    cvs[index], worldSpace=True,
                    translation=[p + d * amount for p, d in zip(position, direction)]
                )

            offset_curves.append(curve)

        cmds.select(clear=True)

        return offset_curves

    def _build_blink_blendshapes(self):
        """
        Monta los tres blendShape del blink. El primer nodo de cada llamada a
        cmds.blendShape es el target de indice 0, el ultimo es la base.

            BlinkHeight   <- eyelidUpperLine        (peso: blinkHeight)
            UpperBlinked  <- UpperNegateBlink, BlinkHeight
            LowerBlinked  <- BlinkHeight, LowerNegateBlink

        La BlinkHeight es a la vez base del primero y target de los otros dos:
        por eso el blinkHeight coloca la linea de cierre y los dos parpados la
        siguen sin tener que recalcular nada.
        """
        blend_shapes = {}

        definitions = [
            ("blinkHeight",  f"{self.prefix}_eyelidBlinkHeight_BLS",
             self.blink_height_curve, [self.upper_curve]),
            ("upperBlinked", f"{self.prefix}_eyelidUpperBlinked_BLS",
             self.upper_blinked_curve, [self.upper_negate_curve, self.blink_height_curve]),
            ("lowerBlinked", f"{self.prefix}_eyelidLowerBlinked_BLS",
             self.lower_blinked_curve, [self.blink_height_curve, self.lower_negate_curve]),
        ]

        for key, name, base, targets in definitions:
            if cmds.objExists(name):
                cmds.delete(name)

            if not base or not cmds.objExists(base):
                cmds.warning(f"[EyesModule] Falta la base {base}, no se crea {name}.")
                continue
            if not all(t and cmds.objExists(t) for t in targets):
                cmds.warning(f"[EyesModule] Faltan targets para {name}.")
                continue

            blend_shapes[key] = cmds.blendShape(*targets, base, n=name)[0]

        self.blink_blend_shapes = blend_shapes

        return blend_shapes

    def _build_blink_range_network(self, attribute, blend_shape, positive_index, negative_index, base_name):
        """
        Parte el rango -1..1 de un atributo de blink en dos pesos.

        Un unico clamp hace las dos mitades: el canal R deja pasar solo lo
        positivo (min 0, max 1) y el canal G solo lo negativo (min -1, max 0).
        Lo negativo sale con signo, asi que un floatMath lo multiplica por -1
        antes de entrar en el peso, que no admite valores por debajo de cero.
        """
        clamp_name = f"{self.prefix}_{base_name}BlinkRanges_CLM"
        negate_name = f"{self.prefix}_{base_name}BlinkNegate_FLM"

        for name in (clamp_name, negate_name):
            if cmds.objExists(name):
                cmds.delete(name)

        clamp = cmds.createNode("clamp", n=clamp_name)
        cmds.setAttr(f"{clamp}.minR", 0)
        cmds.setAttr(f"{clamp}.maxR", 1)
        cmds.setAttr(f"{clamp}.minG", -1)
        cmds.setAttr(f"{clamp}.maxG", 0)

        cmds.connectAttr(attribute, f"{clamp}.inputR", force=True)
        cmds.connectAttr(attribute, f"{clamp}.inputG", force=True)

        negate = cmds.createNode("floatMath", n=negate_name)
        cmds.setAttr(f"{negate}.operation", 2)   # Multiply
        cmds.setAttr(f"{negate}.floatA", -1)
        cmds.connectAttr(f"{clamp}.outputG", f"{negate}.floatB", force=True)

        cmds.connectAttr(f"{clamp}.outputR",
                         f"{blend_shape}.weight[{positive_index}]", force=True)
        cmds.connectAttr(f"{negate}.outFloat",
                         f"{blend_shape}.weight[{negative_index}]", force=True)

        return clamp, negate

    def _connect_blink_attributes(self):
        """
        Engancha los atributos del control de eye_mid a los pesos.

        blinkHeight va directo al unico peso del primer blendShape; upperBlink
        y lowerBlink pasan por su clamp para repartirse entre el target de
        cierre (BlinkHeight) y el de apertura (NegateBlink).
        """
        ctrl = self._get_attribute_host()
        if not ctrl or not cmds.objExists(ctrl):
            cmds.warning("[EyesModule] No hay control con los atributos, el "
                         "blink queda sin conectar.")
            return None

        blend_shapes = self.blink_blend_shapes or {}

        height_bls = blend_shapes.get("blinkHeight")
        if height_bls:
            cmds.connectAttr(f"{ctrl}.blinkHeight",
                             f"{height_bls}.weight[0]", force=True)

        # En UpperBlinked el target 0 es la apertura y el 1 el cierre;
        # en LowerBlinked es al reves, igual que en la escena de referencia.
        upper_bls = blend_shapes.get("upperBlinked")
        if upper_bls:
            self._build_blink_range_network(
                attribute=f"{ctrl}.upperBlink", blend_shape=upper_bls,
                positive_index=1, negative_index=0, base_name="eyelidUpper")

        lower_bls = blend_shapes.get("lowerBlinked")
        if lower_bls:
            self._build_blink_range_network(
                attribute=f"{ctrl}.lowerBlink", blend_shape=lower_bls,
                positive_index=0, negative_index=1, base_name="eyelidLower")

        return ctrl

    def _build_blink_system(self):
        """
        Curvas, blendShapes y red de drivers del blink, en ese orden.
        Se reconstruye entero en cada build porque _build_eyelid_curves borra y
        recrea las lineas originales, y con ellas mueren sus deformadores.
        """
        if not self._build_blink_curves():
            return None

        # El offset de las NegateBlink va antes de los blendShape: asi la pose
        # de apertura ya esta puesta cuando se calculan los primeros deltas.
        self._offset_negate_curves()

        self._build_blink_blendshapes()

        # Despues de los blendShape, que son los que crean las Orig que hay que
        # conectar, y antes de los drivers.
        self._connect_live_blink_bases()

        self._connect_blink_attributes()

        group_name = f"{self.prefix}_eyelidBlinkCurves_GRP"
        if cmds.objExists(group_name):
            cmds.delete(group_name)

        curves = [self.blink_height_curve,
                  self.upper_blinked_curve, self.lower_blinked_curve,
                  self.upper_negate_curve, self.lower_negate_curve]
        curves = [c for c in curves if c and cmds.objExists(c)]

        self.blink_curves_group = cmds.group(curves, n=group_name)

        if self.rig_module_group and cmds.objExists(self.rig_module_group):
            cmds.parent(self.blink_curves_group, self.rig_module_group)

        cmds.select(clear=True)

        return self.blink_curves_group

    # ------------------------------------------------------------------
    # CURVAS DE LOOP (lo que antes eran los SETS de vertices)
    #
    # Antes el borde del parpado se guardaba como un objectSet con los
    # vertices de la malla. Eso ataba el rig a los indices de vertice del
    # modelo: si el modelador reordenaba, hacia un delete history o cambiaba
    # la topologia, el set apuntaba a otro sitio sin avisar.
    #
    # Ahora el artefacto que se guarda es una CURVA de grado 1 con un CV por
    # vertice del edge loop, construida una sola vez desde la seleccion. La
    # curva es un nodo normal de la escena: se guarda con el archivo, se ve en
    # el viewport, se puede mover y no depende de ningun indice de vertice.
    #
    # De esa curva salen las dos cosas:
    #   - la LINEA del parpado (rebuild a grado 3 / 4 spans = 7 CVs), que es la
    #     que skinean los joints locales y la que usa el blink,
    #   - y los JOINTS de loop, uno por CV de la curva cruda.
    # ------------------------------------------------------------------
    @staticmethod
    def loop_curve_name(side, rig_name, upper=True):
        """
        Nombre de la curva cruda del borde del parpado (un CV por vertice).

        La convencion vive aqui y en ningun sitio mas: la UI la usa para crear
        la curva y el modulo para buscarla.
        """
        line = "eyelidUpperLoop" if upper else "eyelidLowerLoop"

        return f"{side}_{rig_name}_{line}_CRV"

    @staticmethod
    def line_curve_name(side, rig_name, upper=True):
        """Nombre de la linea del parpado (la curva ya rebuildeada a 7 CVs)."""
        line = "eyelidUpperLine" if upper else "eyelidLowerLine"

        return f"{side}_{rig_name}_{line}_CRV"

    @staticmethod
    def build_loop_curve_from_selection(side, rig_name, upper=True,
                                        components=None, inner_reference=None):
        """
        Construye la curva de loop a partir del edge seleccionado en la malla.

        Es el unico paso que necesita el modelo delante. Se hace una vez por
        parpado y por lado, y a partir de ahi el build ya no toca la malla.

        Acepta edges, vertices o caras: se convierte todo a edges antes de
        llamar a polyToCurve. polyToCurve con degree=1 saca exactamente un CV
        por vertice y en orden a lo largo del loop, que es justo lo que se pide.
        Se le borra el history acto seguido: la curva tiene que quedar estatica,
        no viva contra la malla.

        Devuelve (nombre_de_la_curva, numero_de_cvs) o None.
        """
        if components is None:
            components = cmds.ls(selection=True, flatten=True) or []

        # Solo componentes: un transform o un shape no llevan "." en el nombre.
        components = [item for item in components if "." in item]
        if not components:
            cmds.warning("[EyesModule] Selecciona el edge loop del parpado, "
                         "no el objeto entero.")
            return None

        edges = cmds.ls(cmds.polyListComponentConversion(components, toEdge=True) or [],
                        flatten=True)
        if not edges:
            cmds.warning("[EyesModule] La seleccion no da ningun edge.")
            return None

        expected = cmds.ls(cmds.polyListComponentConversion(edges, toVertex=True) or [],
                           flatten=True)

        curve_name = EyesModule.loop_curve_name(side, rig_name, upper=upper)
        if cmds.objExists(curve_name):
            cmds.delete(curve_name)

        cmds.select(edges, replace=True)
        created = cmds.polyToCurve(form=0, degree=1, conformToSmoothMeshPreview=0)
        curve = created[0]

        # Sin esto la curva se queda enganchada a la malla por el nodo
        # polyToCurve y deja de ser una guia: pasa a ser un deformador mas.
        cmds.delete(curve, constructionHistory=True)
        curve = cmds.rename(curve, curve_name)

        cv_count = EyesModule._curve_cv_count(curve)

        if expected and cv_count != len(expected):
            cmds.warning(f"[EyesModule] {curve_name}: {cv_count} CVs para "
                         f"{len(expected)} vertices seleccionados. Lo normal es "
                         f"que la seleccion no sea un loop continuo (hay un "
                         f"salto, o has cogido edges de dos lineas distintas).")

        EyesModule._orient_loop_curve(curve, side=side, inner_reference=inner_reference)

        cmds.setAttr(f"{curve}.lineWidth", 3)
        cmds.select(clear=True)

        side_label = "superior" if upper else "inferior"
        print(f"[EyesModule] {curve_name}: {cv_count} CVs para el parpado {side_label}.")

        return curve, cv_count

    @staticmethod
    def _curve_cv_count(curve):
        """Numero de CVs de una curva, leido de su shape."""
        shape = cmds.listRelatives(curve, shapes=True, noIntermediate=True)
        if not shape:
            return 0

        shape = shape[0]

        if cmds.getAttr(f"{shape}.form") == 2:   # periodica
            return cmds.getAttr(f"{shape}.spans")

        return cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")

    @staticmethod
    def _orient_loop_curve(curve, side="L", inner_reference=None):
        """
        Deja la curva siempre en el mismo sentido: CV[0] en la comisura INTERNA.

        polyToCurve empieza por donde le apetece segun el orden de los edges de
        la seleccion, asi que sin esto la mitad de las veces la curva sale del
        reves. Y el sentido importa en todo lo que viene despues: los pesos de
        CV_WEIGHTS van de interna a externa, y las guias se muestrean en ese
        mismo orden.

        Criterio por defecto: la comisura interna es el extremo mas cercano a la
        linea media de la cara (X mundial 0). Si el personaje no esta centrado
        en el origen, pasa 'inner_reference' (un nodo cualquiera del centro de
        la cara, tipico el guia de la nariz) y se mide contra el.
        """
        cv_count = EyesModule._curve_cv_count(curve)
        if cv_count < 2:
            return curve

        first = cmds.pointPosition(f"{curve}.cv[0]", world=True)
        last = cmds.pointPosition(f"{curve}.cv[{cv_count - 1}]", world=True)

        if inner_reference and cmds.objExists(inner_reference):
            reference = cmds.xform(inner_reference, q=True, ws=True, t=True)
            first_score = sum((a - b) ** 2 for a, b in zip(first, reference))
            last_score = sum((a - b) ** 2 for a, b in zip(last, reference))
        else:
            first_score = abs(first[0])
            last_score = abs(last[0])

        if last_score < first_score:
            cmds.reverseCurve(curve, ch=0, rpo=1)

        return curve

    @staticmethod
    def report_loop_curves(side, rig_name):
        """
        Dice, sin construir nada, que curvas de loop hay y cuantos joints
        saldrian de cada una. Sustituye al antiguo report_loop_sets.
        """
        lines = []

        for upper in (True, False):
            label = "Superior" if upper else "Inferior"
            curve_name = EyesModule.loop_curve_name(side, rig_name, upper=upper)

            matches = cmds.ls(curve_name) or []
            if not matches:
                lines.append(f"{label}: no hay curva de loop ({curve_name}). "
                             f"Selecciona el edge del parpado y creala.")
                continue

            if len(matches) > 1:
                lines.append(f"{label}: OJO, hay {len(matches)} nodos llamados "
                             f"{curve_name}. Limpia la escena antes de fiarte del resto.")

            cv_count = EyesModule._curve_cv_count(curve_name)

            # El parpado superior se queda las dos comisuras; el inferior no,
            # porque son vertices compartidos y saldrian dos joints peleandose.
            joints = cv_count if upper else max(cv_count - 2, 0)

            lines.append(f"{label}: {cv_count} CVs en {curve_name} -> {joints} joints de loop")

        print("\n".join(lines))

        return lines

    # ------------------------------------------------------------------
    # JOINTS DE LOOP
    # ------------------------------------------------------------------
    def _resolve_loop_curve(self, upper=True):
        """
        Curva de loop que hay que usar para ese parpado.

        Si se le paso una explicita manda esa; si no, la de convencion.
        Devuelve None si no existe ninguna: sin curva no hay parpado que valga,
        asi que el build avisa y se para en vez de inventarse posiciones.
        """
        explicit = self.upper_loop_curve if upper else self.lower_loop_curve

        if explicit:
            if cmds.objExists(explicit):
                return explicit
            cmds.warning(f"[EyesModule] No existe la curva {explicit}.")
            return None

        by_convention = self.loop_curve_name(self.side, self.rig_name, upper=upper)

        return by_convention if cmds.objExists(by_convention) else None

    def _get_curve_parameter_range(self, curve):
        """
        Rango de parametros de una curva, leido de su shape.

        No se puede dar por hecho 0-1: estas curvas son grado 3 con 4 spans, asi
        que su rango es 0-4. Si el dia de manana cambia el rebuild, esto sigue
        funcionando.
        """
        shape = self._get_deformed_shape(curve)
        if not shape:
            return None

        return cmds.getAttr(f"{shape}.minValue"), cmds.getAttr(f"{shape}.maxValue")

    def _get_curve_cv_positions(self, curve):
        """Posiciones mundiales de todos los CVs de una curva, en orden."""
        cv_count = self._curve_cv_count(curve)

        return [cmds.pointPosition(f"{curve}.cv[{index}]", world=True)
                for index in range(cv_count)]

    def _filter_loop_cvs(self, curve, positions, include_corners):
        """
        Quita CVs repetidos y, si toca, las dos comisuras.

        Los CVs ya vienen ordenados a lo largo del loop (polyToCurve los saca
        asi), o sea que aqui no hay que ordenar nada: eso era necesario cuando
        los miembros de un set llegaban en orden arbitrario.

        Repetidos: si el edge loop se cierra sobre si mismo o la seleccion tenia
        un vertice de mas, pueden salir dos CVs en el mismo sitio. Se quedan en
        uno solo.
        """
        if not positions:
            return []

        size = self._get_curve_size(curve) or 1.0
        tolerance = size * 1e-4

        unique = []
        for position in positions:
            if unique:
                distance = math.sqrt(sum((a - b) ** 2
                                         for a, b in zip(position, unique[-1])))
                if distance < tolerance:
                    continue
            unique.append(position)

        if not include_corners:
            # Las comisuras son los dos extremos del loop y ya las pone el
            # parpado superior.
            if len(unique) <= 2:
                cmds.warning(f"[EyesModule] {curve} tiene {len(unique)} CVs: al "
                             f"quitar las comisuras no queda ningun joint.")
                return []
            unique = unique[1:-1]

        return unique

    def _get_curve_size(self, curve):
        """
        Diagonal del bounding box de la curva. Solo sirve como referencia de
        escala para decir si una distancia es grande o pequena.
        """
        box = cmds.exactWorldBoundingBox(curve)

        return math.sqrt(sum((box[i + 3] - box[i]) ** 2 for i in range(3)))

    @staticmethod
    def diagnose_loop_curve(side, rig_name, upper=True):
        """
        Imprime, CV a CV, donde cae sobre la linea del parpado y a que distancia.

        Es el equivalente del antiguo diagnose_loop_set. Como leerlo:
          - Distancias pequenas y parametros repartidos por todo el rango: bien.
          - Distancias grandes o todos los parametros pegados a un extremo: la
            curva de loop no corresponde a esta linea. Loop del ojo contrario, o
            una curva duplicada de una build anterior.
        """
        curve_name = EyesModule.loop_curve_name(side, rig_name, upper=upper)
        line_curve = EyesModule.line_curve_name(side, rig_name, upper=upper)

        if not cmds.objExists(curve_name):
            cmds.warning(f"[EyesModule] No existe {curve_name}.")
            return []

        matches = cmds.ls(line_curve) or []
        if not matches:
            cmds.warning(f"[EyesModule] No existe {line_curve}. Construye el rig primero.")
            return []
        if len(matches) > 1:
            cmds.warning(f"[EyesModule] Hay {len(matches)} nodos llamados {line_curve}. "
                         f"Sobra alguno de una build anterior y se esta midiendo "
                         f"contra el equivocado.")

        module = EyesModule(side=side, rig_name=rig_name)
        positions = module._get_curve_cv_positions(curve_name)
        if not positions:
            return []

        line_shape = module._get_deformed_shape(line_curve)
        if not line_shape:
            return []

        node = cmds.createNode("nearestPointOnCurve")
        cmds.connectAttr(f"{line_shape}.worldSpace[0]", f"{node}.inputCurve")

        samples = []
        for index, position in enumerate(positions):
            cmds.setAttr(f"{node}.inPosition", *position)
            closest = cmds.getAttr(f"{node}.position")[0]
            distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(position, closest)))
            samples.append({
                "index": index,
                "parameter": cmds.getAttr(f"{node}.parameter"),
                "distance": distance,
            })

        cmds.delete(node)

        size = module._get_curve_size(line_curve)
        print(f"[EyesModule] {curve_name} contra {line_curve} (la linea mide {size:.3f}):")
        for sample in samples:
            print(f"    cv[{sample['index']:02d}]   u={sample['parameter']:7.4f}   "
                  f"dist={sample['distance']:8.4f}")

        return samples

    def _get_loop_parameters(self, upper=True):
        """
        Parametros sobre la linea del parpado donde cae cada joint de loop.

        Solo sirve para informar y diagnosticar: para colocar los joints se usan
        las posiciones de los CVs, que estan sobre la malla. La linea es una
        aproximacion suave del loop y no pasa exactamente por todos ellos.
        """
        curve = self.upper_curve if upper else self.lower_curve
        if not curve or not cmds.objExists(curve):
            return []

        line_shape = self._get_deformed_shape(curve)
        if not line_shape:
            return []

        positions = self._get_loop_positions(upper=upper)
        if not positions:
            return []

        node = cmds.createNode("nearestPointOnCurve")
        cmds.connectAttr(f"{line_shape}.worldSpace[0]", f"{node}.inputCurve")

        parameters = []
        for position in positions:
            cmds.setAttr(f"{node}.inPosition", *position)
            parameters.append(cmds.getAttr(f"{node}.parameter"))

        cmds.delete(node)

        return parameters

    def _clean_loop_setup(self):
        """
        Borra el setup de loops entero antes de reconstruirlo.

        Aqui no vale el patron de 'si ya existe, lo reutilizo': si pasas de 13
        joints a 9, los cuatro sobrantes se quedarian vivos y skinneando. Los
        pointOnCurveInfo y los aimMatrix son nodos de DG y no cuelgan de ningun
        grupo, asi que se buscan y se borran por nombre aparte.
        """
        marker_group = f"{self.prefix}_eyelidLoopJoints_GRP"
        aim_group = f"{self.prefix}_eyelidLoopAim_GRP"

        for group in (marker_group, aim_group):
            if cmds.objExists(group):
                cmds.delete(group)

        leftovers = []
        for tag in ("_PCI", "_AMX", "_NPC", "_DST", "_RMV"):
            leftovers.extend(cmds.ls(f"{self.prefix}_eyelid*Loop*{tag}") or [])
        if leftovers:
            cmds.delete(leftovers)

        self.loop_positions = {"upper": [], "lower": []}
        self.loop_joints = {"upper": [], "lower": []}
        self.loop_aim_joints = {"upper": [], "lower": []}
        self.loop_aim_ends = {"upper": [], "lower": []}
        self.loop_locators = {"upper": [], "lower": []}
        self.loop_point_infos = {"upper": [], "lower": []}
        self.loop_aim_matrices = {"upper": [], "lower": []}
        self.loop_distances = {"upper": [], "lower": []}
        self.loop_remaps = {"upper": [], "lower": []}

        return marker_group, aim_group

    def _get_loop_positions(self, upper=True):
        """
        Posiciones donde va a caer un joint de loop: un CV de la curva cruda.

        Ya no hay reparto por contador ni proyeccion de vertices. La curva de
        loop tiene un CV por vertice del borde del parpado, asi que el numero de
        joints lo decide la topologia del modelo y no un numero escrito en el
        modulo.
        """
        loop_curve = self._resolve_loop_curve(upper=upper)
        if not loop_curve:
            label = "superior" if upper else "inferior"
            cmds.warning(f"[EyesModule] No hay curva de loop para el parpado "
                         f"{label}. Selecciona el edge en la malla y creala "
                         f"antes de construir.")
            return []

        # El parpado superior se queda las dos comisuras; el inferior no.
        include_corners = upper

        positions = self._get_curve_cv_positions(loop_curve)

        return self._filter_loop_cvs(loop_curve, positions, include_corners)
    def _build_loop_joints(self):
        """
        Crea los joints de loop: marcadores de posicion, sin ninguna conexion.

        No cuelgan de la curva ni de ningun control a proposito. Lo unico que
        hacen es marcar donde esta cada loop del parpado, para que el paso
        siguiente lea su translate y lo proyecte sobre la curva. De ahi saldra
        la cadena de aim, y de la cadena de aim los joints de skinning.

        El numero no aparece por ningun sitio del codigo: es la longitud de la
        lista de posiciones. Se reconstruye entero en cada build.
        """
        marker_group, _ = self._clean_loop_setup()

        self.loop_joints_group = cmds.group(em=True, n=marker_group)

        for key, upper in (("upper", True), ("lower", False)):
            positions = self._get_loop_positions(upper=upper)
            if not positions:
                cmds.warning(f"[EyesModule] No hay posiciones de loop para el parpado {key}.")
                continue

            self.loop_positions[key] = positions
            line_name = "eyelidUpperLoop" if upper else "eyelidLowerLoop"

            for index, position in enumerate(positions):
                cmds.select(clear=True)
                joint = cmds.joint(n=f"{self.prefix}_{line_name}{index + 1:02d}_JNT",
                                   p=position)
                cmds.parent(joint, self.loop_joints_group)

                self.loop_joints[key].append(joint)

        if self.rig_module_group and cmds.objExists(self.rig_module_group):
            cmds.parent(self.loop_joints_group, self.rig_module_group)

        cmds.select(clear=True)

        return self.loop_joints_group

    def _bake_curve_parameter(self, curve_shape, joint, point_info, base_name):
        """
        Deja horneado en point_info.parameter el parametro de la curva que le
        corresponde a la posicion del joint.

        Se hace con un nearestPointOnCurve temporal: se conecta el translate del
        joint a su inPosition, se conecta su parameter al del pointOnCurveInfo
        para que el valor viaje, y acto seguido se rompe la conexion. Al romperla
        el valor se queda escrito como estatico, que es justo lo que hace falta:
        el punto tiene que quedarse clavado en su sitio de la curva y viajar con
        ella, no recalcularse contra un joint que ya no se va a mover.
        """
        nearest = cmds.createNode("nearestPointOnCurve", n=f"{base_name}_NPC")
        cmds.connectAttr(f"{curve_shape}.worldSpace[0]", f"{nearest}.inputCurve")
        cmds.connectAttr(f"{joint}.translate", f"{nearest}.inPosition")

        cmds.connectAttr(f"{nearest}.parameter", f"{point_info}.parameter")
        cmds.disconnectAttr(f"{nearest}.parameter", f"{point_info}.parameter")

        cmds.delete(nearest)

        return cmds.getAttr(f"{point_info}.parameter")

    def _duplicate_eye_aim_chain(self, base_name):
        """
        Duplica la cadena de eye_mid (con su eye_mid_end colgando) y la renombra
        con el nombre del loop al que va a apuntar.

        Se duplica en vez de crear joints nuevos para heredar tal cual la
        orientacion del ojo: asi todas las cadenas de aim salen del mismo sitio y
        con los mismos ejes, y la rotacion que acaben teniendo es solo la que les
        mete el aimMatrix.
        """
        mid_joint = self.eye_joints.get(self.eye_mid)
        if not mid_joint or not cmds.objExists(mid_joint):
            return None

        aim_joint = cmds.duplicate(mid_joint, n=f"{base_name}_JNT")[0]

        children = cmds.listRelatives(aim_joint, children=True, fullPath=True) or []
        joints = [child for child in children
                  if cmds.nodeType(child) == "joint"]

        if not joints:
            cmds.delete(aim_joint)
            cmds.warning("[EyesModule] El joint de eye_mid no tiene end, no se puede "
                         "duplicar la cadena de aim.")
            return None

        aim_end = cmds.rename(joints[0], f"{base_name}End_JNT")

        # El duplicado se trae todo lo que colgase de eye_mid (otros joints,
        # shapes de control, locators...): solo interesa el end.
        extras = [child for child in children
                  if child != joints[0] and cmds.objExists(child)]
        if extras:
            cmds.delete(extras)

        return aim_joint, aim_end

    def _connect_loop_radius(self, aim_joint, aim_end, point_info, base_name):
        """
        Hace que el end de la cadena siga la distancia real entre el centro del
        ojo y el punto de la curva, en vez de quedarse a radio fijo.

        El problema que arregla: el matchTransform de la build deja el end a una
        distancia concreta del centro, y el aimMatrix solo aporta rotacion. O
        sea que el joint solo se puede mover sobre una esfera de radio constante.
        Cuando el control sube, el punto de la curva cambia de distancia al
        centro, el joint se queda en su radio y se descuelga hacia atras. Eso es
        el agujero en el skinning.

            eye_mid.worldMatrix[0] -> DST.inMatrix1
            PCI.position           -> DST.point2
            DST.distance           -> RMV.inputValue
            RMV.outValue           -> aimEnd.translate<eje>

        El remapValue va calibrado para pasar por el reposo con pendiente 1: con
        el rig en reposo la salida es exactamente el translate que dejo el
        matchTransform, asi que enchufarlo no mueve nada. A partir de ahi, cada
        unidad que se aleja el punto es una unidad que se aleja el joint.

        Se usa un remap y no una conexion directa porque asi queda tocable: se
        puede bajar LOOP_RADIUS_FOLLOW para que siga solo una parte, o editar la
        rampa del nodo a mano si hace falta una respuesta no lineal.
        """
        aim_center = self._get_aim_center()
        if not aim_center:
            return None

        axis = self.LOOP_AIM_AXIS
        aim_channel = f"{aim_end}.translate{axis}"

        distance = cmds.createNode("distanceBetween", n=f"{base_name}_DST")
        # point1 se queda en el origen: con inMatrix1 puesta, el punto medido es
        # el propio pivote de eye_mid.
        cmds.connectAttr(f"{aim_center}.worldMatrix[0]", f"{distance}.inMatrix1")
        cmds.connectAttr(f"{point_info}.position", f"{distance}.point2")

        # Valores en reposo, leidos de la escena ya montada
        rest_distance = cmds.getAttr(f"{distance}.distance")
        rest_translate = cmds.getAttr(aim_channel)

        if rest_distance < 1e-6:
            cmds.delete(distance)
            cmds.warning(f"[EyesModule] {base_name}: el punto de la curva coincide con el "
                         "centro del ojo, no se conecta el radio.")
            return None

        margin = rest_distance * self.LOOP_RADIUS_RANGE

        # Si el eje de aim apunta al reves, el translate en reposo es negativo y
        # la pendiente tiene que invertirse con el.
        direction = -1.0 if rest_translate < 0 else 1.0
        output_margin = margin * self.LOOP_RADIUS_FOLLOW * direction

        remap = cmds.createNode("remapValue", n=f"{base_name}_RMV")
        cmds.connectAttr(f"{distance}.distance", f"{remap}.inputValue")
        cmds.setAttr(f"{remap}.inputMin", rest_distance - margin)
        cmds.setAttr(f"{remap}.inputMax", rest_distance + margin)
        cmds.setAttr(f"{remap}.outputMin", rest_translate - output_margin)
        cmds.setAttr(f"{remap}.outputMax", rest_translate + output_margin)

        cmds.connectAttr(f"{remap}.outValue", aim_channel)

        return distance, remap

    def _build_loop_aim(self, joint, upper=True):
        """
        Monta la cadena de aim de un joint de loop.

            Blinked_CRVShape.worldSpace[0] -> PCI.inputCurve
                                              PCI.parameter (horneado del joint)
                                              PCI.position          -> LOC.translate
                                              PCI.position          -> AMX.primaryTargetVector
                                              PCI.normalizedTangent -> AMX.secondaryTargetVector
            eye_mid_JNT.worldMatrix[0]     -> AMX.inputMatrix
            AMX.outputMatrix               -> aimJNT.offsetParentMatrix

        La curva de entrada es la Blinked, no la linea original: es el final de
        la cadena (controles -> base viva -> blendShapes del blink), asi que el
        punto ya lleva dentro movimiento de control y parpadeo.

        El aimMatrix arranca de la matriz mundial de eye_mid, o sea del centro
        del ojo, y apunta al punto de la curva. Como secundario le entra la
        tangente de la curva en ese mismo punto, en modo Align: al ser la
        tangente real y no un vector fijo, el frame aguanta sin degenerarse en
        las comisuras aunque el parpado se deforme.

        El outputMatrix va al offsetParentMatrix del joint duplicado y sus
        valores locales se ponen a cero: si no, la transformacion se aplicaria
        dos veces, una por la matriz y otra por los canales.
        """
        curve = self.upper_blinked_curve if upper else self.lower_blinked_curve
        curve_shape = self._get_deformed_shape(curve)
        aim_center = self._get_aim_center()

        if not curve_shape or not aim_center:
            return None

        base_name = f"{joint.rsplit('_JNT', 1)[0]}Aim"

        # 1. Punto sobre la curva Blinked
        point_info = cmds.createNode("pointOnCurveInfo", n=f"{base_name}_PCI")
        # turnOnPercentage a 0: parameter se lee como parametro real de la curva,
        # no como un 0-1 normalizado.
        cmds.setAttr(f"{point_info}.turnOnPercentage", 0)
        cmds.connectAttr(f"{curve_shape}.worldSpace[0]", f"{point_info}.inputCurve")

        # 2. Parametro horneado a partir de la posicion del joint marcador
        self._bake_curve_parameter(curve_shape, joint, point_info, base_name)

        # 3. Locator conducido por el punto, para poder verlo en el viewport
        locator = cmds.spaceLocator(n=f"{base_name}_LOC")[0]
        cmds.connectAttr(f"{point_info}.position", f"{locator}.translate")

        # 4. aimMatrix desde el centro del ojo hacia el punto
        aim_matrix = cmds.createNode("aimMatrix", n=f"{base_name}_AMX")
        cmds.connectAttr(f"{aim_center}.worldMatrix[0]", f"{aim_matrix}.inputMatrix")
        cmds.connectAttr(f"{point_info}.position", f"{aim_matrix}.primaryTargetVector")
        cmds.connectAttr(f"{point_info}.normalizedTangent",
                         f"{aim_matrix}.secondaryTargetVector")
        cmds.setAttr(f"{aim_matrix}.secondaryMode", 2)   # Align

        # 5. Cadena duplicada de eye_mid, conducida por la matriz
        chain = self._duplicate_eye_aim_chain(base_name)
        if not chain:
            return None

        aim_joint, aim_end = chain

        if self.loop_aim_group and cmds.objExists(self.loop_aim_group):
            cmds.parent(aim_joint, self.loop_aim_group)

        cmds.connectAttr(f"{aim_matrix}.outputMatrix", f"{aim_joint}.offsetParentMatrix")

        for attribute in ("translate", "rotate", "jointOrient"):
            cmds.setAttr(f"{aim_joint}.{attribute}", 0, 0, 0)
        cmds.setAttr(f"{aim_joint}.scale", 1, 1, 1)

        # El end se lleva al loop DESPUES de que la matriz ya conduzca al padre,
        # para que su translate local salga medido contra la cadena ya colocada.
        cmds.matchTransform(aim_end, joint, position=True)

        # Y el radio se conecta DESPUES del match, que es de donde salen los
        # valores de reposo con los que se calibra el remap.
        radius = self._connect_loop_radius(aim_joint, aim_end, point_info, base_name)
        distance, remap = radius if radius else (None, None)

        if self.loop_aim_group and cmds.objExists(self.loop_aim_group):
            cmds.parent(locator, self.loop_aim_group)

        return aim_joint, aim_end, locator, point_info, aim_matrix, distance, remap

    def _build_loop_aims(self):
        """
        Monta la cadena de aim de todos los joints de loop de los dos parpados.

        Va despues de _build_loop_joints, que es quien deja los marcadores de
        los que se hornea el parametro de cada punto. Ojo: aqui no se vuelve a
        llamar a _clean_loop_setup, que se llevaria por delante esos marcadores.
        """
        if not self.upper_blinked_curve or not self.lower_blinked_curve:
            cmds.warning("[EyesModule] Sin curvas de blink no se monta el aim de los loops.")
            return None

        group_name = f"{self.prefix}_eyelidLoopAim_GRP"
        if cmds.objExists(group_name):
            cmds.delete(group_name)

        self.loop_aim_group = cmds.group(em=True, n=group_name)

        for key, upper in (("upper", True), ("lower", False)):
            for joint in self.loop_joints[key]:
                built = self._build_loop_aim(joint, upper=upper)
                if not built:
                    continue

                aim_joint, aim_end, locator, point_info, aim_matrix, distance, remap = built

                self.loop_aim_joints[key].append(aim_joint)
                self.loop_aim_ends[key].append(aim_end)
                self.loop_locators[key].append(locator)
                self.loop_point_infos[key].append(point_info)
                self.loop_aim_matrices[key].append(aim_matrix)
                self.loop_distances[key].append(distance)
                self.loop_remaps[key].append(remap)

        if self.rig_module_group and cmds.objExists(self.rig_module_group):
            cmds.parent(self.loop_aim_group, self.rig_module_group)

        cmds.select(clear=True)

        return self.loop_aim_group

    # ------------------------------------------------------------------
    # ORGANIZACION DEL OUTLINER
    #
    # Mismo reparto que leg_module y limbs_module: el SISTEMA cuelga del
    # <rig>_rig_GRP y los CONTROLES del <rig>_local_CTL.
    #
    #     <rig>_rig_GRP
    #         |- C_<rig>_face_GRP
    #              |- C_<rig>_eyes_GRP
    #                   |- L_<rig>_eyes_GRP
    #                   |- R_<rig>_eyes_GRP
    #
    #     <rig>_local_CTL
    #         |- C_<rig>_faceControls_GRP
    #              |- C_<rig>_eyesControls_GRP
    #                   |- L_<rig>_eyesControls_GRP
    #                   |- R_<rig>_eyesControls_GRP
    #
    # El <rig>_mirrorBehaviour_GRP no se usa: los faciales van con sistema
    # local. Nada entra ahi y nada sale de ahi.
    # ------------------------------------------------------------------
    def _ensure_group(self, group_name, parent_group=None):
        """
        Devuelve `group_name`, creandolo vacio en la raiz del mundo si no
        existe. Idempotente: se puede llamar en cada build sin duplicar.
        """
        if cmds.objExists(group_name):
            group_node = group_name
        else:
            group_node = cmds.group(em=True, world=True, n=group_name)

        if parent_group and cmds.objExists(parent_group):
            current_parent = cmds.listRelatives(group_node, parent=True) or []
            if not current_parent or current_parent[0] != parent_group:
                cmds.parent(group_node, parent_group, relative=True)

        return group_node

    def _park_node(self, node_name, destination_group):
        """
        Mete `node_name` en `destination_group` SOLO si esta suelto en la raiz
        de la escena.

        Si ya tiene padre no se toca: esa jerarquia si es funcional (un OFF de
        Sub que cuelga del TRN de su principal, un _GRP dentro del TRN del
        fleshy, lo que hubiera en el mirrorBehaviour_GRP).

        El parent es RELATIVO: el grupo destino esta en identidad, asi que
        conservar los valores locales conserva la matriz de mundo exacta y no
        se mueve nada.
        """
        if not node_name or not cmds.objExists(node_name):
            return False
        if not cmds.objExists(destination_group):
            return False
        if cmds.listRelatives(node_name, parent=True):
            return False

        try:
            cmds.parent(node_name, destination_group, relative=True)
        except Exception as error:
            cmds.warning(f"EyesModule: no se pudo ordenar '{node_name}' dentro "
                         f"de '{destination_group}': {error}")
            return False
        return True

    def _get_aim_center(self):
        """
        Transform estatico en el centro del ojo, del que cuelgan el aimMatrix y
        el distanceBetween de todos los loops.

        No sirve eye_mid_JNT para esto. Ese joint va con parentConstraint contra
        su control, o sea que sigue a la cabeza, mientras que las curvas Blinked
        viven en el espacio local estatico y no se mueven. Con la cabeza quieta
        da igual, pero en cuanto se separa:

          - el aimMatrix compara dos espacios y la direccion se va,
          - y sobre todo, el distanceBetween mide una distancia que crece sin
            freno y el remapValue la mete en el translate del AimEnd. El joint
            se estira igual que una IK con stretch y revienta la geometria.

        Este transform se coloca una vez en el centro del ojo y se queda ahi, en
        el mismo espacio que las curvas, asi que toda la red de aim es coherente
        y estatica. La cabeza entra despues y por fuera, en el grupo de salida
        (_attach_eyes_to_head), que es como funciona el modulo de la boca.

        eye_mid_JNT no se toca: sigue conduciendo el globo ocular y el fleshy.
        """
        center_name = f"{self.prefix}_eyeAimCenter_TRN"
        if cmds.objExists(center_name):
            return center_name

        mid_joint = self.eye_joints.get(self.eye_mid)
        if not mid_joint or not cmds.objExists(mid_joint):
            return None

        center = cmds.group(em=True, n=center_name)
        cmds.matchTransform(center, mid_joint, position=True, rotation=True)

        # Al grupo de marcadores, que es estatico. NO al de aim, que es el que
        # se constriñe a la cabeza.
        marker_group = f"{self.prefix}_eyelidLoopJoints_GRP"
        if cmds.objExists(marker_group):
            cmds.parent(center, marker_group)

        return center

    def _attach_eyes_to_head(self):
        """
        NO constriñe nada. Se conserva como sitio documentado del porque.

        Antes ponia un parentConstraint del head_JNT en eyelidLoopAim_GRP, y eso
        hacia que los *AimEnd_JNT (los que skinean) siguiesen a la cabeza. Con el
        montaje de dos mallas eso es justo lo que no puede pasar: la malla facial
        tiene que quedarse clavada en bind para que la blendShape solo le pase a
        la malla de body mechanics el delta de expresion. Si los joints de skin
        se mueven con la cabeza, ese movimiento entra por la blendShape y se suma
        al que la otra malla ya tiene por su propio skinCluster.

        Los CONTROLES si siguen a la cabeza, pero por otra via: _organize_outliner
        los cuelga de C_<rig>_faceControls_GRP, que es el grupo compartido que el
        modulo de jaw constriñe en _attach_face_controls_to_head. Esa es
        exactamente la reparticion que hace que el jaw funcione: controles arriba
        con la cabeza, joints de skin quietos abajo.

        Si algun dia se quita el montaje de dos mallas, aqui es donde volveria el
        constraint del grupo de aim.
        """
        return None

    def _face_systems_root(self):
        """C_<rig>_face_GRP, bajo el rig_GRP. Compartido con boca y jaw."""
        rig_grp = f"{self.rig_name}_rig_GRP"
        if self.root_instance is not None and hasattr(self.root_instance, "get_rig_grp"):
            rig_grp = self.root_instance.get_rig_grp()

        parent = rig_grp if cmds.objExists(rig_grp) else None
        return self._ensure_group(f"C_{self.rig_name}_face_GRP", parent)

    def _face_controls_root(self):
        """C_<rig>_faceControls_GRP, bajo el local_CTL. Compartido con boca y jaw."""
        local_ctl = f"{self.rig_name}_local_CTL"
        if self.root_instance is not None:
            local_ctl = getattr(self.root_instance, "localCtl", None) or local_ctl

        parent = local_ctl if cmds.objExists(local_ctl) else None
        return self._ensure_group(f"C_{self.rig_name}_faceControls_GRP", parent)

    def _organize_outliner(self):
        """
        Ordena lo que este modulo deja suelto en la raiz.

        Se llama al final de build(). Es idempotente y lo ya colocado se
        ignora por el chequeo de padre de _park_node().
        """
        rig = self.rig_name
        center = f"C_{rig}"

        # --- 1. Esqueleto ---
        systems_grp = self._ensure_group(f"{center}_eyes_GRP", self._face_systems_root())
        side_systems_grp = self._ensure_group(f"{self.prefix}_eyes_GRP", systems_grp)

        controls_grp = self._ensure_group(f"{center}_eyesControls_GRP",
                                          self._face_controls_root())
        side_controls_grp = self._ensure_group(f"{self.prefix}_eyesControls_GRP",
                                               controls_grp)

        # --- 2. Controles ---
        # Raices del fleshy: despues de _build_fleshy_setup son ellas las que
        # cuelgan los _GRP de parpados y esquinas, asi que es lo que se mueve.
        control_roots = [data.get("off") for data in self.fleshy_nodes.values()]

        # Los que no pasan por el fleshy: intermedios, eye_mid y eye_direct.
        # Los Sub cuelgan de su control principal y se arrastran solos.
        fleshy_guides = {guide for setup in self.fleshy_setups
                         for guide in setup["guides"]}
        control_roots.extend(ctrl_grp for guide, ctrl_grp
                             in self.eye_control_groups.items()
                             if guide not in fleshy_guides)
        control_roots.append(self.eye_direct_control_group)

        for group_node in control_roots:
            self._park_node(group_node, side_controls_grp)

        # --- 3. Sistema ---
        # _group_rig_module ya recogio los OFF del setup local, y el grupo de
        # joints, las curvas de blink y los loops ya se meten ahi segun se
        # crean. Aqui se coloca ese grupo y se barre lo que quede suelto.
        self._park_node(self.rig_module_group, side_systems_grp)
        self._park_node(self.joints_group, side_systems_grp)

        # Red de seguridad, para no depender de una lista de nombres que se
        # queda corta en cuanto el modulo cree un nodo nuevo. Solo _GRP y _CRV:
        # las guias no llevan esos sufijos y se quedan fuera.
        for pattern in (f"{self.prefix}_*_GRP", f"{self.prefix}_*_CRV"):
            for node in cmds.ls(pattern, type="transform") or []:
                self._park_node(node, side_systems_grp)

        # --- 4. La salida del aim sigue a la cabeza ---
        # Al final a proposito: el grupo tiene que estar ya colocado para que el
        # maintain offset del constraint salga limpio.
        self._attach_eyes_to_head()

        return side_systems_grp

    def organize_outliner(self):
        """
        Version publica, para volver a barrer la raiz despues de que hayan
        corrido otros modulos. Idempotente.
        """
        return self._organize_outliner()

    def _group_rig_module(self):
        """
        Mete todo el setup local (OFF, TRN y sus joints) bajo un unico grupo del
        modulo, junto al grupo de settings ya creado.

        Solo se emparentan los nodos que estan en la raiz de la escena: los OFF de
        los Sub cuelgan del TRN de su principal y los joints cuelgan de su TRN,
        asi que se arrastran solos y la jerarquia no se toca.
        """
        module_name = f"{self.prefix}_eyeLidRigModule_GRP"

        if cmds.objExists(module_name):
            # Saca lo que hubiera dentro antes de borrarlo, para no perder el setup
            children = cmds.listRelatives(module_name, children=True, fullPath=True) or []
            if children:
                cmds.parent(children, world=True)
            cmds.delete(module_name)

        self.rig_module_group = cmds.group(em=True, n=module_name)

        if self.settings_group and cmds.objExists(self.settings_group):
            cmds.parent(self.settings_group, self.rig_module_group)

        # Candidatos: todos los OFF del setup local (principales y Sub), mas el
        # grupo de fleshy local, que ahora es quien tiene colgados los OFF de los
        # cuatro parpados principales.
        candidates = list(self.eye_local_offs.values()) + list(self.eye_sub_local_offs.values())
        candidates.extend(data.get("local_off") for data in self.fleshy_nodes.values())

        for node in candidates:
            if not node or not cmds.objExists(node):
                continue

            # Solo los que estan sueltos en la raiz: los demas ya cuelgan de su TRN
            if cmds.listRelatives(node, parent=True):
                continue

            cmds.parent(node, self.rig_module_group)

        cmds.select(clear=True)

        return self.rig_module_group

    def build(self):
        """
        Metodo principal del modulo. Construye los joints del ojo a partir de las guias,
        las curvas de los parpados y un control (con sus grupos y su setup local) por joint.
        Las esquinas y los parpados central superior e inferior llevan un segundo control (Sub);
        en esos casos el joint local solo se crea en el Sub, no en el principal.
        Los controles intermedios (02 y 03) quedan conducidos por sus dos vecinos con el
        reparto que manda el grupo de settings, se skinean las curvas a los joints locales
        y se agrupa todo el setup del modulo.
        """
        # =========================================================
        # LINEAS DE LOS PARPADOS
        # Van las PRIMERAS: ahora son la fuente de la que salen las posiciones
        # de los joints de parpado, no al reves. Sin curva de loop en la escena
        # no hay nada que construir, asi que se para aqui.
        # =========================================================
        self._build_eyelid_curves()
        if self.upper_curve is None or self.lower_curve is None:
            cmds.warning("[EyesModule] Faltan las curvas de loop. Selecciona el "
                         "edge de cada parpado y creala con "
                         "build_loop_curve_from_selection.")
            return None

        self._build_eye_joints()
        if self.joints_group is None:
            return None

        # Cadena del ojo: eye_mid_end colgando del joint de eye_mid.
        self._build_eye_mid_end_joint()

        # =========================================================
        # CONTROLES + GRUPOS + SETUP LOCAL (OFF / TRN) POR CADA JOINT
        # Mismo patron que levator / depresor / pinch de la boca.
        # =========================================================
        self.eye_controls = {}
        self.eye_control_groups = {}
        self.eye_local_offs = {}
        self.eye_local_trns = {}
        self.eye_local_joints = {}

        self.eye_sub_controls = {}
        self.eye_sub_control_groups = {}
        self.eye_sub_local_offs = {}
        self.eye_sub_local_trns = {}
        self.eye_sub_local_joints = {}

        for guide, joint in self.eye_joints.items():
            ctrl_name = f"{self.prefix}_{guide}_CTRL"
            if not cmds.objExists(ctrl_name):
                ctrl = controlsLibrary.create_control_from_lib(
                    lib_name=self.styles["eyelid"],
                    final_name=ctrl_name
                )

                ctrl_grp = self.group_maker.create_rig_hierarchy(
                    ctrl, joint, match_rotation=True, world_space=True
                )
            else:
                ctrl = ctrl_name
                ctrl_grp = cmds.listRelatives(ctrl, parent=True)[0]

            # El eye_mid se queda solo con el control: nada de OFF/TRN.
            # Su joint no skinea ninguna curva de parpado, asi que no necesita
            # el espacio local; va conducido por un parentConstraint directo
            # (_constrain_eye_mid_joint) y el _GRP lo orienta el aim.
            if guide == self.eye_mid:
                self.eye_controls[guide] = ctrl
                self.eye_control_groups[guide] = ctrl_grp
                self._delete_local_setup(guide)
                continue

            off_name = f"{self.prefix}_{guide}Local_OFF"
            trn_name = f"{self.prefix}_{guide}Local_TRN"
            if not cmds.objExists(off_name):
                local_off, local_trn = self._build_off_network(
                    prefix=self.prefix, base_name=guide,
                    source_ctrl=ctrl, source_ctrl_grp=ctrl_grp
                )
            else:
                local_off, local_trn = off_name, trn_name

            self.eye_controls[guide] = ctrl
            self.eye_control_groups[guide] = ctrl_grp
            self.eye_local_offs[guide] = local_off
            self.eye_local_trns[guide] = local_trn

            # ---- Segundo control (Sub) solo en esquinas y parpados centrales ----
            if guide not in self.sub_control_guides:
                continue

            sub_ctrl_name = f"{self.prefix}_{guide}Sub_CTRL"
            if not cmds.objExists(sub_ctrl_name):
                sub_ctrl = controlsLibrary.create_control_from_lib(
                    lib_name=self.styles["eyelidSub"],
                    final_name=sub_ctrl_name
                )

                sub_ctrl_grp = self.group_maker.create_rig_hierarchy(
                    sub_ctrl, joint, match_rotation=True, world_space=True
                )
                # El Sub cuelga del control principal para que herede su movimiento
                cmds.parent(sub_ctrl_grp, ctrl)
            else:
                sub_ctrl = sub_ctrl_name
                sub_ctrl_grp = cmds.listRelatives(sub_ctrl, parent=True)[0]

            sub_off_name = f"{self.prefix}_{guide}SubLocal_OFF"
            sub_trn_name = f"{self.prefix}_{guide}SubLocal_TRN"
            if not cmds.objExists(sub_off_name):
                # El OFF del Sub cuelga del TRN del principal: misma jerarquia que los controles
                sub_local_off, sub_local_trn = self._build_off_network(
                    prefix=self.prefix, base_name=f"{guide}Sub",
                    source_ctrl=sub_ctrl, source_ctrl_grp=sub_ctrl_grp,
                    parent_group=local_trn
                )
            else:
                sub_local_off, sub_local_trn = sub_off_name, sub_trn_name

            self.eye_sub_controls[guide] = sub_ctrl
            self.eye_sub_control_groups[guide] = sub_ctrl_grp
            self.eye_sub_local_offs[guide] = sub_local_off
            self.eye_sub_local_trns[guide] = sub_local_trn

        # =========================================================
        # CONTROL DE EYE_DIRECT + AIM DEL OJO
        # El _GRP del control de eye_mid apunta al control de eye_direct, y el
        # joint de eye_mid sigue a su control: mover el direct rota el ojo.
        # =========================================================
        self._build_eye_direct_control()
        self._aim_eye_mid_to_direct()
        self._constrain_eye_mid_joint()

        # =========================================================
        # ATRIBUTOS EXTRA DE BLINK EN EL CONTROL DEL OJO
        # Separador + upperBlink / lowerBlink / blinkHeight.
        #
        # Va DESPUES del eyeDirect a proposito: el documento pide que estos
        # atributos vivan en ese control, asi que tiene que existir ya cuando
        # _get_attribute_host lo busca.
        # =========================================================
        self._add_blink_attributes()

        # La shape del control de eye_mid se dibuja sobre el joint de
        # eye_mid_end; el transform y el pivote no se mueven.
        self._offset_eye_mid_shape()

        # =========================================================
        # FLESHY EYE
        # Los parpados orbitan con la mirada segun el atributo fleshy del
        # control de eye_mid. Va antes de los constraints y de la agrupacion
        # para que se hagan con la jerarquia ya en su sitio.
        # =========================================================
        self._build_fleshy_setup()

        # =========================================================
        # EJES DE LOS CONTROLES DEL LADO R
        # Aqui y no al final: los controles intermedios se colocan con un
        # parentConstraint contra sus dos vecinos y con mo=True, asi que el
        # offset tiene que medirse con la escala ya volteada. Si se voltea
        # despues, ese offset se aplica sobre un marco invertido y los cuatro
        # intermedios se meten hacia el centro del ojo.
        #
        # Y despues del fleshy porque ese paso reparenta los _GRP de parpados
        # y esquinas: asi se voltea lo que ya esta en su sitio definitivo.
        # =========================================================
        self._mirror_control_axes()

        # =========================================================
        # GRUPO DE SETTINGS
        # Va antes de los constraints porque sus atributos conducen los pesos.
        # =========================================================
        self.settings_group = self._build_settings_group()

        # =========================================================
        # CONSTRAINTS DE LOS CONTROLES INTERMEDIOS (02 y 03)
        # El GRP del intermedio sigue a los dos controles vecinos, y su OFF local
        # sigue a los dos TRN locales vecinos: mismo comportamiento en los joints.
        # Los pesos los manda el atributo de follow (directo + reverse).
        # =========================================================
        self._constrain_in_between()

        # =========================================================
        # JOINTS DEL SETUP LOCAL (segunda pasada)
        # Se crean ahora, con la jerarquia de OFF/TRN ya cerrada, para que
        # queden como hojas y ningun OFF cuelgue de un joint.
        # Si la guia tiene Sub, solo se crea el joint del Sub.
        # =========================================================
        for guide, local_trn in self.eye_local_trns.items():
            if guide in self.sub_control_guides:
                # Solo se queda el joint del Sub: se borra el del principal si venia de otra build
                old_joint = local_trn.rsplit("_TRN", 1)[0] + "_JNT"
                if cmds.objExists(old_joint):
                    cmds.delete(old_joint)
                self.eye_local_joints[guide] = None
                continue

            self.eye_local_joints[guide] = self._create_local_joint(local_trn)

        for guide, sub_local_trn in self.eye_sub_local_trns.items():
            self.eye_sub_local_joints[guide] = self._create_local_joint(sub_local_trn)

        # =========================================================
        # SKINNING DE LAS CURVAS A LOS JOINTS LOCALES
        # =========================================================
        self.upper_skin_cluster = self._skin_eyelid_curve(self.upper_curve, upper=True)
        self.lower_skin_cluster = self._skin_eyelid_curve(self.lower_curve, upper=False)

        # =========================================================
        # AGRUPACION DEL MODULO
        # Todo el setup local (OFF/TRN y sus joints) mas el grupo de settings.
        # =========================================================
        self._group_rig_module()

        # =========================================================
        # SISTEMA DE BLINK
        # Va al final: necesita las lineas ya skinneadas, el control des
        # eye_mid con sus atributos y el grupo del modulo ya creado.
        # =========================================================
        self._build_blink_system()

        # =========================================================
        # JOINTS DE LOOP
        # Uno por cada loop del parpado en la malla. Van conducidos por las
        # curvas Blinked, que son el final de la cadena, asi que tienen que ir
        # despues del sistema de blink.
        # =========================================================
        self._build_loop_joints()

        # =========================================================
        # CADENA DE AIM DE LOS LOOPS
        # Un pointOnCurveInfo sobre la curva Blinked y un aimMatrix desde el
        # centro del ojo por cada marcador. De aqui saldran los joints de
        # skinning.
        # =========================================================
        self._build_loop_aims()

        # =========================================================
        # ORGANIZACION DEL OUTLINER
        # Lo ultimo: cuando ya no queda nada por crear ni por reparentar.
        # =========================================================
        self._organize_outliner()

        cmds.select(clear=True)

        return self.joints_group