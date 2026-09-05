import math

import maya.cmds as cmds    
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class EyesModule(object):

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

    # Atributos de follow del grupo de settings: (nombre_largo, nombre_visible)
    SETTINGS_ATTRIBUTES = [
        ("Up01FollowUp", "Up 01 Follow Up"),
        ("Up03FollowUp", "Up 03 Follow Up"),
        ("Low01FollowLow", "Low 01 Follow Low"),
        ("Low03FollowLow", "Low 03 Follow Low"),
    ]

    # Atributos extra de los controles centrales de los parpados:
    # (nombre_largo, nombre_visible, valor_por_defecto). Todos van de -1 a 1.
    BLINK_ATTRIBUTES = [
        ("upperBlink", "Upper Blink", 0.0),
        ("lowerBlink", "Lower Blink", 0.0),
        ("blinkHeight", "Blink Height", 0.2),
    ]

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
                 upper_loop_count=13,
                 lower_loop_count=13,
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
        # Hay dos formas de decidir cuantos y donde:
        #   - Sin malla: se reparten *_loop_count parametros a lo largo de la curva.
        #   - Con malla: un objectSet con los vertices del borde del parpado, y
        #     cada vertice da su parametro exacto sobre la curva.
        # Si hay set, el set manda y el contador se ignora.
        #
        # *_loop_set a None NO significa "no uses set": significa "buscalo por
        # convencion de nombre" (loop_set_name). Asi el mismo build funciona con
        # modelo y sin el, sin tocar una linea: si el set esta en la escena se
        # usa, y si no esta se cae al contador. Solo hay que pasar un nombre a
        # mano si el set se llama de otra forma.
        self.upper_loop_count = upper_loop_count
        self.lower_loop_count = lower_loop_count
        self.upper_loop_set = upper_loop_set
        self.lower_loop_set = lower_loop_set

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

    def _build_eye_joints(self):
        """
        Crea un joint nuevo por cada joint de guia del ojo, en la misma posicion y orientacion.
        Los agrupa todos bajo un unico grupo del modulo.
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

        for guide in guides:
            # Acepta la guia con lado ("L_eye_mid") o sin el ("eye_mid")
            guide_node = None
            if cmds.objExists(guide):
                guide_node = guide
            elif cmds.objExists(f"{self.side}_{guide}"):
                guide_node = f"{self.side}_{guide}"

            if guide_node is None:
                cmds.warning(f"[EyesModule] No se encontro la guia {guide}, se omite su joint.")
                continue

            joint_name = f"{self.prefix}_{guide}_JNT"
            if cmds.objExists(joint_name):
                cmds.delete(joint_name)

            cmds.select(clear=True)
            new_joint = cmds.joint(name=joint_name)
            cmds.matchTransform(new_joint, guide_node, position=True, rotation=True)

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

    def _build_eyelid_curves(self):
        """
        Crea las curvas de curvatura de los parpados (superior e inferior):
        1. Curva de grado 1 con 7 CVs: los 5 joints de la linea mas 2 CVs intermedios,
           uno entre cada esquina y el secundario contiguo (donde no hay joint).
        2. rebuildCurve a grado 3, 4 spans (4+3 = 7 CVs -> mismo conteo, misma correspondencia).

        Solo se construye cuando existen los 5 joints de esa linea. Si falta alguno, no hace nada.
        """
        for upper in (True, False):
            line_name = "eyelidUpperLine" if upper else "eyelidLowerLine"
            curve_name = f"{self.prefix}_{line_name}_CRV"

            if cmds.objExists(curve_name):
                cmds.delete(curve_name)

            ordered_joints = self._get_ordered_eyelid_joints(upper=upper)
            if not all(cmds.objExists(jnt) for jnt in ordered_joints):
                cmds.warning(f"[EyesModule] Faltan joints para construir {curve_name}.")
                continue

            joint_positions = [cmds.xform(jnt, q=True, ws=True, t=True) for jnt in ordered_joints]

            # Punto medio entre esquina interna (0) y secundario interno (1)
            inner_extra = [(a + b) * 0.5 for a, b in zip(joint_positions[0], joint_positions[1])]
            # Punto medio entre secundario externo (3) y esquina externa (4)
            outer_extra = [(a + b) * 0.5 for a, b in zip(joint_positions[3], joint_positions[4])]

            positions = [
                joint_positions[0],   # esquina interna
                inner_extra,          # CV extra sin joint
                joint_positions[1],   # secundario interno
                joint_positions[2],   # centro del parpado
                joint_positions[3],   # secundario externo
                outer_extra,          # CV extra sin joint
                joint_positions[4],   # esquina externa
            ]

            curve_transform = cmds.curve(d=1, p=positions, n=curve_name)
            cmds.rebuildCurve(
                curve_transform, ch=0, rpo=1, rt=0, end=1, kr=0, kcp=0, kep=1, kt=0,
                s=4, d=3, tol=0.01
            )
            cmds.setAttr(f"{curve_transform}.lineWidth", 3)

            if upper:
                self.upper_curve = curve_transform
            else:
                self.lower_curve = curve_transform

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
        old_controls = [
            self.eye_controls.get(self.eyelid_up),
            self.eye_controls.get(self.eyelid_low),
        ]

        attr_names = ["extraAttrSep"] + [name for name, _, _ in self.BLINK_ATTRIBUTES]

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

    def _add_blink_attributes(self):
        """
        Anade al control de eye_mid el separador de atributos extra y los tres
        floats de blink.

        Idempotente: si el atributo ya existe en el control no se vuelve a crear,
        asi que se puede relanzar la build sin que reviente.
        """
        ctrl = self.eye_controls.get(self.eye_mid)
        if not ctrl or not cmds.objExists(ctrl):
            cmds.warning(f"[EyesModule] No existe el control de {self.eye_mid}, "
                         "no se anaden los atributos de blink.")
            return None

        # Los atributos vivian en los parpados: se limpian de ahi antes de nada.
        self._clean_old_blink_attributes()

        if not cmds.attributeQuery("extraAttrSep", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="extraAttrSep", nn="EXTRA_ATTR",
                         at="enum", en="------", k=False)

        # Con k=False el enum existe pero no se ve: hay que marcarlo en el
        # Channel Box y bloquearlo para que se pinte como separador.
        cmds.setAttr(f"{ctrl}.extraAttrSep", channelBox=True, lock=True)

        for long_name, nice_name, default_value in self.BLINK_ATTRIBUTES:
            if cmds.attributeQuery(long_name, node=ctrl, exists=True):
                continue

            cmds.addAttr(
                ctrl, ln=long_name, nn=nice_name,
                at="float", min=-1, max=1, dv=default_value, k=True
            )

        return ctrl

    def _add_fleshy_attribute(self, setup):
        """
        Anade al control de eye_mid el float de un setup de fleshy.

        A 0 esos controles no se enteran de por donde mira el ojo; a 1 le siguen
        todo lo que permita su multiplicador. El defecto es 0, asi que montar el
        sistema no cambia nada hasta que alguien lo sube a mano.
        """
        ctrl = self.eye_controls.get(self.eye_mid)
        if not ctrl or not cmds.objExists(ctrl):
            cmds.warning(f"[EyesModule] No existe el control de {self.eye_mid}, "
                         "no se anaden los atributos de fleshy.")
            return None

        long_name = setup["attribute"]

        if not cmds.attributeQuery(long_name, node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln=long_name, nn=setup["nice_name"],
                         at="float", min=0, max=1, dv=0.0, k=True)

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

        for long_name, nice_name in self.SETTINGS_ATTRIBUTES:
            cmds.addAttr(
                settings_group, ln=long_name, nn=nice_name,
                at="float", min=0, max=1, dv=0.5, k=True
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
        ctrl = self.eye_controls.get(self.eye_mid)
        if not ctrl or not cmds.objExists(ctrl):
            cmds.warning("[EyesModule] No existe el control de eye_mid, el blink queda sin conectar.")
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
    # SETS DE LOOP (convencion de nombre + helpers para la UI)
    # ------------------------------------------------------------------
    @staticmethod
    def loop_set_name(side, rig_name, upper=True):
        """
        Nombre del objectSet con los vertices del borde del parpado.

        La convencion vive aqui y en ningun sitio mas: la UI la usa para crear
        el set y el modulo para buscarlo. Si se escribiera en los dos lados,
        cualquier cambio dejaria de encontrarlo en silencio.
        """
        line = "eyelidUpperLoop" if upper else "eyelidLowerLoop"

        return f"{side}_{rig_name}_{line}_SET"

    @staticmethod
    def save_loop_set(side, rig_name, upper=True, components=None):
        """
        Guarda la seleccion actual como set de loop, con el nombre de convencion.

        Acepta vertices, edges o caras: lo normal es seleccionar un edge loop,
        asi que se convierte a vertices antes de guardar. Lo que no acepta es el
        objeto entero, porque polyListComponentConversion devolveria toda la
        malla y el set saldria con miles de vertices sin que salte ningun error.

        Devuelve (nombre_del_set, numero_de_vertices) o None si no hay nada
        aprovechable en la seleccion.
        """
        if components is None:
            components = cmds.ls(selection=True, flatten=True) or []

        # Solo componentes: un transform o un shape no llevan "." en el nombre
        components = [item for item in components if "." in item]
        if not components:
            cmds.warning("[EyesModule] Selecciona el loop de vertices o edges del parpado, "
                         "no el objeto entero.")
            return None

        converted = cmds.polyListComponentConversion(components, toVertex=True) or []
        vertices = cmds.ls(converted, flatten=True) or []
        if not vertices:
            cmds.warning("[EyesModule] La seleccion no da ningun vertice.")
            return None

        set_name = EyesModule.loop_set_name(side, rig_name, upper=upper)

        if cmds.objExists(set_name):
            cmds.delete(set_name)

        cmds.sets(vertices, n=set_name)

        side_label = "superior" if upper else "inferior"
        print(f"[EyesModule] {set_name}: {len(vertices)} vertices guardados "
              f"para el parpado {side_label}.")

        return set_name, len(vertices)

    @staticmethod
    def report_loop_sets(side, rig_name):
        """
        Dice, sin construir nada, que sets hay y cuantos joints saldrian.

        Si la linea del parpado ya existe en la escena se calculan tambien los
        parametros de verdad, que es lo unico que te confirma que el descarte de
        comisuras y el filtro de duplicados hacen lo que esperas. Sirve para no
        lanzar builds a ciegas cuando la distribucion no cuadra.
        """
        lines = []

        for upper in (True, False):
            label = "Superior" if upper else "Inferior"
            set_name = EyesModule.loop_set_name(side, rig_name, upper=upper)

            if not cmds.objExists(set_name):
                lines.append(f"{label}: no hay set ({set_name}). Se usara el contador.")
                continue

            members = cmds.sets(set_name, q=True) or []
            converted = cmds.polyListComponentConversion(members, toVertex=True) or []
            vertices = cmds.ls(converted, flatten=True) or []

            detail = ""
            line_curve = f"{side}_{rig_name}_" + (
                "eyelidUpperLine_CRV" if upper else "eyelidLowerLine_CRV")

            matches = cmds.ls(line_curve) or []
            if len(matches) > 1:
                lines.append(f"{label}: OJO, hay {len(matches)} nodos llamados "
                             f"{line_curve}. Limpia la escena antes de fiarte del resto.")

            if matches:
                module = EyesModule(side=side, rig_name=rig_name)
                if upper:
                    module.upper_curve = line_curve
                else:
                    module.lower_curve = line_curve

                parameters = module._get_loop_parameters(upper=upper)

                # La distancia media es lo que separa "el set es correcto" de
                # "el set es de otra curva": los parametros solos no lo dicen.
                samples = module._sample_loop_set(line_curve, set_name)
                if samples:
                    average = sum(s["distance"] for s in samples) / len(samples)
                    size = module._get_curve_size(line_curve)
                    detail = (f" -> {len(parameters)} joints"
                              f" (dist. media {average:.3f} sobre una curva de {size:.3f})")
                else:
                    detail = f" -> {len(parameters)} joints"

            lines.append(f"{label}: {len(vertices)} vertices en {set_name}{detail}")

        print("\n".join(lines))

        return lines

    # ------------------------------------------------------------------
    # JOINTS DE LOOP
    # ------------------------------------------------------------------
    def _resolve_loop_set(self, upper=True):
        """
        Set que hay que usar para ese parpado.

        Si se le paso uno explicito manda ese; si no, se busca el de convencion.
        Devuelve None si no existe ninguno, que es la senal de caer al contador.
        """
        explicit = self.upper_loop_set if upper else self.lower_loop_set

        if explicit:
            if cmds.objExists(explicit):
                return explicit
            cmds.warning(f"[EyesModule] No existe el set {explicit}, se usa el contador.")
            return None

        by_convention = self.loop_set_name(self.side, self.rig_name, upper=upper)

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

    def _get_loop_parameters_from_count(self, curve, count, include_corners):
        """
        Reparte 'count' parametros a lo largo de la curva, sin necesidad de malla.

        En el parpado superior se incluyen las dos esquinas; en el inferior no,
        porque las esquinas son vertices compartidos por los dos parpados y si
        las pone tambien el de abajo acabas con dos joints peleandose en el mismo
        sitio.

        Ojo: repartir uniforme en parametro no es repartir uniforme en espacio.
        Los joints salen algo mas juntos donde la curva tiene mas curvatura. Para
        una primera pasada da igual, y con el camino del set esto ni se aplica.
        """
        parameter_range = self._get_curve_parameter_range(curve)
        if not parameter_range or count < 1:
            return []

        minimum, maximum = parameter_range
        span = maximum - minimum

        if include_corners:
            if count == 1:
                return [minimum + span * 0.5]
            return [minimum + span * (index / float(count - 1)) for index in range(count)]

        # Estrictamente por dentro: ni la primera ni la ultima caen en la esquina
        return [minimum + span * ((index + 1) / float(count + 1)) for index in range(count)]

    def _sample_loop_set(self, curve, loop_set):
        """
        Proyecta cada vertice del set sobre la curva y devuelve, por vertice,
        su parametro y a que distancia estaba.

        La distancia es la que permite detectar el fallo mas comun y mas
        silencioso: que el set no corresponda a esa curva (loop del lado
        contrario, curva duplicada de una build anterior, malla movida). Cuando
        pasa eso nearestPointOnCurve no falla, sino que clava todos los vertices
        contra el extremo mas cercano de la curva, y los 13 parametros salen
        practicamente identicos.

        Devuelve [] si no hay nada que muestrear.
        """
        if not loop_set or not cmds.objExists(loop_set):
            return []

        members = cmds.sets(loop_set, q=True) or []
        if not members:
            cmds.warning(f"[EyesModule] El set {loop_set} esta vacio.")
            return []

        converted = cmds.polyListComponentConversion(members, toVertex=True) or []
        vertices = cmds.ls(converted, flatten=True) or []
        if not vertices:
            cmds.warning(f"[EyesModule] No se sacan vertices de {loop_set}.")
            return []

        curve_shape = self._get_deformed_shape(curve)
        if not curve_shape:
            return []

        node = cmds.createNode("nearestPointOnCurve")
        cmds.connectAttr(f"{curve_shape}.worldSpace[0]", f"{node}.inputCurve")

        samples = []
        for vertex in vertices:
            position = cmds.pointPosition(vertex, world=True)
            cmds.setAttr(f"{node}.inPosition", *position)

            closest = cmds.getAttr(f"{node}.position")[0]
            distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(position, closest)))

            samples.append({
                "vertex": vertex,
                "parameter": cmds.getAttr(f"{node}.parameter"),
                "distance": distance,
            })

        cmds.delete(node)

        return samples

    def _filter_loop_samples(self, curve, loop_set, samples, include_corners):
        """
        Ordena las muestras a lo largo de la curva, quita las que caen en el
        mismo sitio y, si toca, descarta las comisuras.

        Lo usan tanto el camino de parametros como el de posiciones, para que
        los dos apliquen exactamente los mismos criterios.
        """
        if not samples:
            return []

        parameter_range = self._get_curve_parameter_range(curve)
        if not parameter_range:
            return []

        minimum, maximum = parameter_range
        span = maximum - minimum

        # El orden de los miembros de un set es arbitrario y aqui hace falta ir
        # de comisura a comisura.
        ordered = sorted(samples, key=lambda sample: sample["parameter"])

        # Dos vertices distintos pueden caer practicamente en el mismo sitio de
        # la curva: se queda solo uno.
        unique = []
        for sample in ordered:
            if unique and abs(sample["parameter"] - unique[-1]["parameter"]) < span * 1e-4:
                continue
            unique.append(sample)

        # Si el colapso es masivo, el set no encaja con esta curva. Sin este
        # aviso el modulo construiria un joint suelto y tan tranquilo.
        if len(unique) < len(ordered) * 0.5:
            worst = max(sample["distance"] for sample in ordered)
            size = self._get_curve_size(curve)
            cmds.warning(
                f"[EyesModule] {loop_set}: {len(ordered)} vertices se han quedado en "
                f"{len(unique)} parametros sobre {curve}. El vertice mas lejano esta a "
                f"{worst:.3f} (la curva mide {size:.3f}). Revisa que el set sea el loop "
                f"de este parpado y de este lado."
            )

        if not include_corners:
            # Los vertices de las comisuras caen pegados a los extremos del rango.
            # Son los que ya pone el parpado superior, asi que aqui se descartan.
            tolerance = span * 0.02
            unique = [sample for sample in unique
                      if (sample["parameter"] - minimum) > tolerance
                      and (maximum - sample["parameter"]) > tolerance]

        return unique

    def _get_loop_parameters_from_set(self, curve, loop_set, include_corners):
        """
        Parametros sobre la curva, uno por vertice del set. Sirve para informar
        y diagnosticar; para colocar los joints se usan las posiciones.
        """
        samples = self._sample_loop_set(curve, loop_set)
        filtered = self._filter_loop_samples(curve, loop_set, samples, include_corners)

        return [sample["parameter"] for sample in filtered]

    def _get_loop_positions_from_set(self, curve, loop_set, include_corners):
        """
        Posiciones de los vertices del set, ordenadas a lo largo de la curva.

        Se devuelve la posicion del vertice, no la del punto proyectado sobre la
        curva: el joint tiene que caer sobre la malla, que es donde de verdad
        esta el loop. La proyeccion solo se usa para ordenarlos y para descartar
        repetidos y comisuras.
        """
        samples = self._sample_loop_set(curve, loop_set)
        filtered = self._filter_loop_samples(curve, loop_set, samples, include_corners)

        return [cmds.pointPosition(sample["vertex"], world=True) for sample in filtered]

    def _get_curve_size(self, curve):
        """
        Diagonal del bounding box de la curva. Solo sirve como referencia de
        escala para decir si una distancia es grande o pequena.
        """
        box = cmds.exactWorldBoundingBox(curve)

        return math.sqrt(sum((box[i + 3] - box[i]) ** 2 for i in range(3)))

    @staticmethod
    def diagnose_loop_set(side, rig_name, upper=True):
        """
        Imprime, vertice a vertice, en que parametro de la curva cae y a que
        distancia estaba. Es lo que hay que mirar cuando el check dice que 13
        vertices dan 1 joint.

        Como leerlo:
          - Distancias pequenas y parametros repartidos por todo el rango: bien.
          - Distancias grandes y todos los parametros iguales (o pegados a 0 o al
            maximo): el set no es de esta curva. Loop del ojo contrario, o una
            curva duplicada de una build anterior.
          - Vertices sueltos con distancia mucho mayor que el resto: se te ha
            colado algun vertice que no es del loop.
        """
        set_name = EyesModule.loop_set_name(side, rig_name, upper=upper)
        line_curve = f"{side}_{rig_name}_" + (
            "eyelidUpperLine_CRV" if upper else "eyelidLowerLine_CRV")

        if not cmds.objExists(set_name):
            cmds.warning(f"[EyesModule] No existe {set_name}.")
            return []

        matches = cmds.ls(line_curve) or []
        if not matches:
            cmds.warning(f"[EyesModule] No existe {line_curve}. Construye el rig primero.")
            return []
        if len(matches) > 1:
            cmds.warning(f"[EyesModule] Hay {len(matches)} nodos llamados {line_curve}. "
                         f"Sobra alguno de una build anterior y se esta midiendo contra "
                         f"el equivocado.")

        module = EyesModule(side=side, rig_name=rig_name)
        samples = module._sample_loop_set(line_curve, set_name)
        if not samples:
            return []

        size = module._get_curve_size(line_curve)
        print(f"[EyesModule] {set_name} contra {line_curve} (la curva mide {size:.3f}):")
        for sample in sorted(samples, key=lambda s: s["parameter"]):
            print(f"    u={sample['parameter']:7.4f}   dist={sample['distance']:8.4f}   "
                  f"{sample['vertex']}")

        return samples

    def _get_loop_parameters(self, upper=True):
        """
        Devuelve la lista de parametros donde va a caer un joint de loop.

        El set se busca con _resolve_loop_set: el explicito si se paso uno, y si
        no el de convencion. Si hay set manda el set y el contador se ignora; si
        no hay (o sale vacio), se cae al reparto por contador. Asi el modulo
        construye igual con modelo que sin el, sin tocar el build.

        Los parametros se miden sobre la linea original del parpado, que es la
        que esta en reposo y encaja con la malla. La curva Blinked que luego
        conduce los joints es un duplicado suyo, asi que comparte
        parametrizacion y los valores valen tal cual.
        """
        curve = self.upper_curve if upper else self.lower_curve
        if not curve or not cmds.objExists(curve):
            return []

        loop_set = self._resolve_loop_set(upper=upper)
        count = self.upper_loop_count if upper else self.lower_loop_count

        # El parpado superior se queda las dos comisuras; el inferior no.
        include_corners = upper

        parameters = self._get_loop_parameters_from_set(curve, loop_set, include_corners)

        if not parameters:
            parameters = self._get_loop_parameters_from_count(curve, count, include_corners)

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
        Posiciones donde va a caer un joint de loop.

        Con set: la posicion real de cada vertice del borde del parpado.
        Sin set: puntos repartidos sobre la linea del parpado, que es lo unico
        que hay cuando no hay malla.
        """
        curve = self.upper_curve if upper else self.lower_curve
        if not curve or not cmds.objExists(curve):
            return []

        # El parpado superior se queda las dos comisuras; el inferior no.
        include_corners = upper

        loop_set = self._resolve_loop_set(upper=upper)
        if loop_set:
            positions = self._get_loop_positions_from_set(curve, loop_set, include_corners)
            if positions:
                return positions

        count = self.upper_loop_count if upper else self.lower_loop_count
        parameters = self._get_loop_parameters_from_count(curve, count, include_corners)

        return [cmds.pointOnCurve(curve, pr=parameter, position=True)
                for parameter in parameters]

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
        mid_joint = self.eye_joints.get(self.eye_mid)
        if not mid_joint or not cmds.objExists(mid_joint):
            return None

        axis = self.LOOP_AIM_AXIS
        aim_channel = f"{aim_end}.translate{axis}"

        distance = cmds.createNode("distanceBetween", n=f"{base_name}_DST")
        # point1 se queda en el origen: con inMatrix1 puesta, el punto medido es
        # el propio pivote de eye_mid.
        cmds.connectAttr(f"{mid_joint}.worldMatrix[0]", f"{distance}.inMatrix1")
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
        mid_joint = self.eye_joints.get(self.eye_mid)

        if not curve_shape or not mid_joint or not cmds.objExists(mid_joint):
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
        cmds.connectAttr(f"{mid_joint}.worldMatrix[0]", f"{aim_matrix}.inputMatrix")
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
        self._build_eye_joints()
        if self.joints_group is None:
            return None

        # Cadena del ojo: eye_mid_end colgando del joint de eye_mid.
        self._build_eye_mid_end_joint()

        self._build_eyelid_curves()

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
        # ATRIBUTOS EXTRA DE BLINK EN EL CONTROL DEL OJO
        # Separador + upperBlink / lowerBlink / blinkHeight en el control de eye_mid.
        # =========================================================
        self._add_blink_attributes()

        # =========================================================
        # CONTROL DE EYE_DIRECT + AIM DEL OJO
        # El _GRP del control de eye_mid apunta al control de eye_direct, y el
        # joint de eye_mid sigue a su control: mover el direct rota el ojo.
        # =========================================================
        self._build_eye_direct_control()
        self._aim_eye_mid_to_direct()
        self._constrain_eye_mid_joint()

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

        cmds.select(clear=True)

        return self.joints_group