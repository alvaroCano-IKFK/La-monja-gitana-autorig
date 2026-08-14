import maya.cmds as cmds    
import maya.mel as mel
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class JawModule(object):
    
    def __init__(self, 
                 jaw_root="jaw_root", 
                 jaw_end="jaw_end", 
                 root_instance=None, 
                 mouth_instances=None,      
                 rig_name="Character",
                 side="C"):
        

        self.jaw_root = jaw_root
        self.jaw_end = jaw_end
        self.group_maker = ControlsGroups()
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.mouth_instances = mouth_instances or []
        self.styles = {"mainFk": "squareControl"}
        
        self.side = side
        self.prefix = f"{self.side}_{rig_name}"

        # Nodos que expone el modulo para que otros (la boca) puedan
        # engancharse sin tener que reconstruir los nombres a mano.
        self.jaw_upper_jnt = None
        self.jaw_lower_jnt = None
        self.jaw_upper_ctrl = None
        self.jaw_lower_ctrl = None
        self.jaw_upper_local_trn = None
        self.jaw_lower_local_trn = None
        self.corner_joints = {}
        self.lip_bind_joints = {}
        
        
    def _offset_control_shape(self, ctrl, move=(0, 0, 0), rotate=(0, 0, 0), scale=1.0):
        """
        Mueve/rota/escala las CVs de un control sin tocar su transform.
        El pivote no se mueve y los canales quedan a 0.
        """
        shapes = cmds.listRelatives(ctrl, shapes=True, type="nurbsCurve", fullPath=True) or []
        if not shapes:
            cmds.warning(f"[Jaw] '{ctrl}' no tiene shapes de curva.")
            return

        # Todas las CVs de todas las shapes, de golpe
        cvs = []
        for shape in shapes:
            cvs.extend(cmds.ls(f"{shape}.cv[*]", flatten=True))

        pivot = cmds.xform(ctrl, q=True, ws=True, rp=True)

        if any(rotate):
            cmds.rotate(rotate[0], rotate[1], rotate[2], cvs, r=True, p=pivot, os=True)
        if scale != 1.0:
            cmds.scale(scale, scale, scale, cvs, r=True, p=pivot)
        if any(move):
            cmds.move(move[0], move[1], move[2], cvs, r=True, os=True)    

    def _get_rig_group(self, ctrl_grp, suffix):
        """
        Devuelve el grupo con ese sufijo dentro de la jerarquia que crea
        create_rig_hierarchy (GRP > SPC > OFF > SDK > ANIM).

        :param ctrl_grp: el _GRP raiz que devuelve create_rig_hierarchy
        :param suffix:   'SPC', 'OFF', 'SDK' o 'ANIM'
        """
        for node in cmds.listRelatives(ctrl_grp, allDescendents=True, type="transform") or []:
            if node.endswith(f"_{suffix}"):
                return node
        cmds.warning(f"[Jaw] No encuentro el grupo '_{suffix}' bajo '{ctrl_grp}'.")
        return None

    def _get_local_mult_matrix(self, ctrl):
        """
        Devuelve el multMatrix que cuelga del '.matrix' de un control.

        Lo buscamos por conexion y no por nombre: el sufijo final lo decide
        NodeCreator, asi que reconstruirlo con un f-string es fragil.
        '.matrix' es un output del control, asi que el multMatrix esta en el
        lado DESTINO de la conexion (source=False, destination=True).

        :param ctrl: nombre del control (ej. 'C_Character_jawLower_CTRL')
        :return:     nombre del multMatrix o None si no existe
        """
        if not cmds.objExists(ctrl):
            cmds.warning(f"[Jaw] El control '{ctrl}' no existe.")
            return None

        nodes = cmds.listConnections(
            f"{ctrl}.matrix",
            source=False,
            destination=True,
            type="multMatrix"
        ) or []

        if not nodes:
            cmds.warning(f"[Jaw] No encuentro ningun multMatrix conectado a '{ctrl}.matrix'.")
            return None

        return nodes[0]

    def _build_off_network(self, prefix, base_name, source_ctrl, source_ctrl_grp):
        """
        Crea el space-tracking local (_OFF / _TRN) de un control: el _TRN
        replica el movimiento LOCAL del control (su .matrix), no el global.

        Devuelve (local_off, local_trn).
        """
        local_off, local_trn = self.group_maker.create_space_tracking_hierarchy(
            space_base_name=f"{prefix}_{base_name}Local",
            target_joint=source_ctrl_grp,
            parent_group=None
        )

        mult_node = NodeCreator(
            side=prefix, node_type="multMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        decompose_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        # OJO: antes este nodo se creaba con los mismos argumentos que el
        # anterior, asi que Maya le metia un sufijo numerico para desambiguar.
        # Con un 'name' distinto el nombre queda limpio y predecible.
        decompose_trn_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="LocalTrn", tag="CTRL", parent=None, custom_suffix=None
        ).create()

        cmds.connectAttr(f"{source_ctrl}.matrix", f"{mult_node}.matrixIn[0]")
        cmds.connectAttr(f"{mult_node}.matrixSum", f"{decompose_node}.inputMatrix")
        cmds.connectAttr(f"{decompose_node}.outputTranslate", f"{local_trn}.translate")
        cmds.connectAttr(f"{decompose_node}.outputRotate", f"{local_trn}.rotate")
        cmds.connectAttr(f"{decompose_node}.outputScale", f"{local_trn}.scale")
        cmds.connectAttr(f"{local_trn}.worldMatrix[0]", f"{decompose_trn_node}.inputMatrix")

        return local_off, local_trn

    def _constrain_joint_to_local_trn(self, local_trn, joint):
        """
        El _TRN conduce al joint. No al reves: los canales del _TRN ya vienen
        conectados desde el decomposeMatrix de _build_off_network, asi que no
        admite ser destino de un constraint.
        """
        if not cmds.objExists(local_trn):
            cmds.warning(f"[Jaw] No existe el TRN '{local_trn}'.")
            return None
        if not cmds.objExists(joint):
            cmds.warning(f"[Jaw] No existe el joint '{joint}'.")
            return None

        existing = cmds.listRelatives(joint, type="parentConstraint") or []
        if existing:
            return existing[0]

        return cmds.parentConstraint(local_trn, joint, mo=True)[0]

    # ------------------------------------------------------------------
    # COMISURAS DE LA BOCA
    # ------------------------------------------------------------------
    def _get_mouth_corner_controls(self):
        """
        Devuelve {side: ctrl} de las comisuras de la boca (end_LIP_CTRL).

        Primero mira las instancias de MouthModule que nos hayan pasado;
        si no hay, cae al nombre en escena. El nombre es determinista
        ({side}_{rig_name}_end_LIP_CTRL), asi que el fallback es seguro.
        """
        corners = {}

        for mouth in self.mouth_instances:
            ctrl = getattr(mouth, "end_lip_ctrl", None)
            if ctrl and cmds.objExists(ctrl):
                corners[mouth.side] = ctrl

        if not corners:
            for side in ("L", "R"):
                ctrl = f"{side}_{self.rig_name}_end_LIP_CTRL"
                if cmds.objExists(ctrl):
                    corners[side] = ctrl

        if not corners:
            cmds.warning("[Jaw] No encuentro las comisuras de la boca. "
                         "Construye el MouthModule antes que el jaw.")
        return corners

    def _create_corner_joints(self):
        """
        Crea un JNT por comisura, en la posicion del control y orientado
        como el jaw_root (para que el rotateX del jaw sea el eje limpio).
        """
        corners = self._get_mouth_corner_controls()
        corner_joints = {}

        for side, ctrl in corners.items():
            jnt_name = f"{side}_{self.rig_name}_jawCorner_JNT"
            if cmds.objExists(jnt_name):
                corner_joints[side] = jnt_name
                continue

            pos = cmds.xform(ctrl, q=True, ws=True, t=True)
            cmds.select(clear=True)
            jnt = cmds.joint(n=jnt_name, p=pos)
            cmds.matchTransform(jnt, self.jaw_root, rot=True, pos=False)
            cmds.makeIdentity(jnt, apply=True, r=True)

            corner_joints[side] = jnt

        return corner_joints

    def _constrain_corner_joints(self, corner_joints, jaw_upper_jnt,
                                 jaw_lower_jnt, driver_ctrl):
        """
        Constrainea cada comisura entre jawUpper y jawLower.

        Los dos pesos van conectados con valores complementarios: uno recibe
        el atributo {side}UpperLower directo y el otro el mismo atributo
        pasado por un reverse, para que el slider recorra de extremo a extremo.
        """
        constraints = {}

        for side, corner_jnt in corner_joints.items():
            attr = f"{driver_ctrl}.{side}UpperLower"
            if not cmds.objExists(attr):
                cmds.warning(f"[Jaw] No existe el atributo '{attr}'.")
                continue

            existing = cmds.listRelatives(corner_jnt, type="parentConstraint") or []
            if existing:
                constraints[side] = existing[0]
                continue

            # mo=True es obligatorio: la comisura esta desplazada del pivote
            # del jaw, sin offset se teletransportaria al centro.
            constraint = cmds.parentConstraint(
                jaw_upper_jnt, jaw_lower_jnt, corner_jnt, mo=True
            )[0]
            cmds.setAttr(f"{constraint}.interpType", 2)  # Shortest, evita flips

            # Emparejamos alias con target por nombre, no por indice: el orden
            # de los targets no siempre coincide con el orden en que los pasamos.
            targets = cmds.parentConstraint(constraint, q=True, targetList=True)
            weights = cmds.parentConstraint(constraint, q=True, weightAliasList=True)
            alias_by_target = dict(zip(targets, weights))

            upper_weight = alias_by_target[jaw_upper_jnt]
            lower_weight = alias_by_target[jaw_lower_jnt]

            reverse_node = NodeCreator(
                side=f"{side}_{self.rig_name}", node_type="reverse",
                base_name="jawCorner", name="UpperLower", tag="CTRL",
                parent=None, custom_suffix=None
            ).create()
            cmds.connectAttr(attr, f"{reverse_node}.inputX")

            if side == "L":
                cmds.connectAttr(attr, f"{constraint}.{upper_weight}")
                cmds.connectAttr(f"{reverse_node}.outputX", f"{constraint}.{lower_weight}")
            else:
                cmds.connectAttr(f"{reverse_node}.outputX", f"{constraint}.{upper_weight}")
                cmds.connectAttr(attr, f"{constraint}.{lower_weight}")

            constraints[side] = constraint

        return constraints

    # ------------------------------------------------------------------
    # LINEAS DE PINCH DEL JAW
    # ------------------------------------------------------------------
    def _get_pinch_curve_pairs(self):
        """
        {label: (curva_pinch_de_la_boca, copia_JawPinchLine)}

        Los nombres de la boca son constantes deterministas. No los saco de
        las instancias de MouthModule porque _build_lip_curve tiene un early
        return: en cualquier build posterior esas variables ni se asignan.
        """
        return {
            "Upper": (f"C_{self.rig_name}_lipCurvatureUpperPinch_CRV",
                      f"C_{self.rig_name}_lipUpperJawPinchLine_CRV"),
            "Lower": (f"C_{self.rig_name}_lipCurvatureLowerPinch_CRV",
                      f"C_{self.rig_name}_lipLowerJawPinchLine_CRV"),
        }

    def _build_jaw_pinch_lines(self):
        """
        Duplica las curvas de pinch de la boca y conecta el worldSpace de
        la original al create de la copia, para que la siga ya deformada.
        """
        pinch_lines = {}

        for label, (src_curve, dup_name) in self._get_pinch_curve_pairs().items():
            if not cmds.objExists(src_curve):
                cmds.warning(f"[Jaw] No existe la curva de pinch '{src_curve}'. "
                             "Construye el MouthModule antes que el jaw.")
                continue

            if cmds.objExists(dup_name):
                pinch_lines[label] = dup_name
                continue

            dup_curve = cmds.duplicate(src_curve, n=dup_name)[0]
            # La copia no debe arrastrar deformadores propios: su unica
            # entrada tiene que ser el worldSpace de la original.
            cmds.delete(dup_curve, ch=True)

            # ni=True es clave: la curva de pinch esta skineada, asi que tiene
            # una shape intermedia (Orig). Sin el filtro te puede tocar esa.
            src_shape = cmds.listRelatives(src_curve, shapes=True, ni=True, f=True)[0]
            dup_shape = cmds.listRelatives(dup_curve, shapes=True, ni=True, f=True)[0]

            cmds.connectAttr(f"{src_shape}.worldSpace[0]", f"{dup_shape}.create", force=True)

            pinch_lines[label] = dup_curve

        return pinch_lines

    def _bind_jaw_pinch_lines(self, corner_joints):
        """
        Skinea las curvas JawPinchLine con las dos comisuras mas un ancla
        central, y encadena cada skinCluster al worldSpace de su curva de
        pinch de origen.

        El centro de las dos lineas va anclado al freeze_JNT, que no se mueve
        nunca. Los labios ya siguen a la mandibula desde el modulo de la boca
        ('_link_lip_to_jaw'), asi que la apertura llega por la cadena de curvas
        y volver a aplicarla aqui seria una doble transformacion: la curva
        bajaria el doble que la de la boca.

        Lo que si aporta esta linea, y no puede venir de la cadena, es la
        mezcla upper/lower de las comisuras: en las curvas de la boca los
        cv[0] y cv[6] estan anclados al freeze y no se enteran del jaw. Aqui
        los lleva el jawCorner_JNT de cada lado, que es quien blendea con el
        slider LUpperLower / RUpperLower.

        El orden de CVs va de comisura a comisura, asi que cv[0] cae en el
        lado L y cv[6] en el R.
        """
        L_corner = corner_joints.get("L")
        R_corner = corner_joints.get("R")
        freeze_joint = f"C_{self.rig_name}_freeze_JNT"

        if not cmds.objExists(freeze_joint):
            cmds.warning(f"[Jaw] No existe '{freeze_joint}'. "
                         "Construye el MouthModule antes que el jaw.")
            return {}

        corner_influences = [j for j in (L_corner, R_corner)
                             if j and cmds.objExists(j)]

        if len(corner_influences) < 2:
            cmds.warning(f"[Jaw] Solo tengo {len(corner_influences)} de 2 comisuras. "
                         "Revisa que existan antes de skinear.")
            return {}

        skins = {}

        for label, (src_curve, dup_curve) in self._get_pinch_curve_pairs().items():
            if not cmds.objExists(dup_curve):
                cmds.warning(f"[Jaw] No existe '{dup_curve}'. "
                             "Lanza _build_jaw_pinch_lines antes.")
                continue

            existing = cmds.listConnections(dup_curve, type="skinCluster")
            if existing:
                skins[label] = existing[0]
                continue

            cv_count = len(cmds.ls(f"{dup_curve}.cv[*]", flatten=True))
            if cv_count != 7:
                cmds.warning(f"[Jaw] '{dup_curve}' tiene {cv_count} CVs, esperaba 7. "
                             "No asigno pesos por CV.")

            # Cada curva se skinea con el ancla central mas las dos comisuras.
            # Nada de dejar influencias a peso 0 colgando.
            mid = freeze_joint
            influences = [mid] + corner_influences

            # Paso los joints como argumentos en vez de con cmds.select:
            # asi el bind no depende de lo que haya seleccionado el usuario.
            skin_cluster = cmds.skinCluster(
                *influences, dup_curve,
                tsb=True, bm=0, sm=0, nw=1, wd=0, mi=1, dr=4.0
            )[0]

            # Los CVs centrales tambien van explicitos: con tres influencias,
            # dejarlos por distancia haria que las comisuras sangraran al centro.
            cv_weights = {
                0: [(L_corner, 1.0)],
                1: [(L_corner, 0.5), (mid, 0.5)],
                2: [(mid, 1.0)],
                3: [(mid, 1.0)],
                4: [(mid, 1.0)],
                5: [(R_corner, 0.5), (mid, 0.5)],
                6: [(R_corner, 1.0)],
            }

            if cv_count == 7:
                for cv_index, transform_value in cv_weights.items():
                    cmds.skinPercent(
                        skin_cluster, f"{dup_curve}.cv[{cv_index}]",
                        transformValue=transform_value
                    )

            # Mismo encadenado que usas en la boca: el skinCluster parte de la
            # posicion YA deformada de la curva de pinch, no de la copia
            # estatica (Orig) que crea el bind.
            src = f"{src_curve}.worldSpace[0]"
            for dst in (f"{skin_cluster}.input[0].inputGeometry",
                        f"{skin_cluster}.originalGeometry[0]"):
                if not cmds.isConnected(src, dst):
                    cmds.connectAttr(src, dst, force=True)

            skins[label] = skin_cluster

        return skins

    # ------------------------------------------------------------------
    # EL JAW ARRASTRA AL LABIO INFERIOR
    # ------------------------------------------------------------------
    def _build_jaw_delta_matrix(self, label, jaw_ctrl, jaw_ctrl_grp):
        """
        multMatrix con el delta MUNDIAL de un control del jaw:

            GRP_raiz.worldInverseMatrix * control.worldMatrix

        En reposo los dos son la misma matriz, asi que el delta sale identidad
        y no mueve nada. Al rotar el control es la transformacion que hay que
        aplicarle a cualquier cosa para que acompañe a la mandibula, ya con el
        pivote correcto (el jaw_root), sin conjugar nada despues.

        Leo el control y no su TRN local a proposito: el TRN solo copia
        'ctrl.matrix', asi que se pierde todo lo que venga del SDK — y ahi es
        justo donde entra el sistema de colision del upper. Cerrando contra el
        _GRP raiz se cancela lo que haya por encima (la cabeza) y se recoge
        todo lo que haya por debajo.
        """
        node_name = f"{self.prefix}_jaw{label}Delta_MMX"
        if cmds.objExists(node_name):
            return node_name

        if not cmds.objExists(jaw_ctrl) or not cmds.objExists(jaw_ctrl_grp):
            cmds.warning(f"[Jaw] Falta el control o el _GRP del {label} para el delta.")
            return None

        mult_node = NodeCreator(
            side=self.prefix, node_type="multMatrix", base_name=f"jaw{label}Delta",
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        mult_node = cmds.rename(mult_node, node_name)

        cmds.connectAttr(f"{jaw_ctrl_grp}.worldInverseMatrix[0]", f"{mult_node}.matrixIn[0]")
        cmds.connectAttr(f"{jaw_ctrl}.worldMatrix[0]", f"{mult_node}.matrixIn[1]")

        return mult_node

    def _build_jaw_driven_locator(self, label, source_locator, delta_node, locator_name):
        """
        Locator cuyo mundo es 'source_locator' con el delta del jaw aplicado
        encima. Todo va por offsetParentMatrix y los canales quedan a 0, asi
        que no hay nada que se pueda mover a mano por error.
        """
        if cmds.objExists(locator_name):
            return locator_name

        if not cmds.objExists(source_locator) or not delta_node:
            cmds.warning(f"[Jaw] No puedo montar '{locator_name}': "
                         f"falta '{source_locator}' o el delta del jaw.")
            return None

        mult_node = NodeCreator(
            side=self.prefix, node_type="multMatrix", base_name=f"jaw{label}Driven",
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()

        cmds.connectAttr(f"{source_locator}.worldMatrix[0]", f"{mult_node}.matrixIn[0]")
        cmds.connectAttr(f"{delta_node}.matrixSum", f"{mult_node}.matrixIn[1]")

        driven_locator = cmds.spaceLocator(name=locator_name)[0]
        cmds.connectAttr(f"{mult_node}.matrixSum", f"{driven_locator}.offsetParentMatrix")

        return driven_locator

    def _retarget_parent_constraint(self, node, driver):
        """
        Sustituye el parentConstraint que ya tenga 'node' por uno nuevo hacia
        'driver'. Idempotente: si el driver ya es el target, no toca nada.

        Hay que borrar y rehacer, no añadir un target: dos targets en un
        parentConstraint blendean posiciones, no las suman, y aqui lo que
        queremos es sustituir el centro limpio por el centro con mandibula.
        """
        if not cmds.objExists(node) or not driver or not cmds.objExists(driver):
            return None

        for constraint in cmds.listRelatives(node, children=True, type="parentConstraint") or []:
            targets = cmds.parentConstraint(constraint, q=True, targetList=True) or []
            if driver in targets:
                return constraint
            cmds.delete(constraint)

        return cmds.parentConstraint(driver, node, mo=True)[0]

    def _find_constrained_ancestor(self, node):
        """
        Sube por la jerarquia desde 'node' hasta el primer transform que tenga
        un parentConstraint colgando.

        Lo busco asi y no por sufijo porque el _GRP raiz que constriñe la boca
        lo devuelve create_rig_hierarchy, y reconstruir ese nombre a mano con
        un f-string sobre un control que ademas ya viene renombrado es pedir
        problemas.
        """
        current = node
        while current:
            if cmds.listRelatives(current, children=True, type="parentConstraint"):
                return current
            parents = cmds.listRelatives(current, parent=True, type="transform")
            current = parents[0] if parents else None
        return None

    def _link_lip_to_jaw(self, label, jaw_ctrl, jaw_ctrl_grp):
        """
        Engancha un labio de la boca a su mitad de la mandibula.

        'label' es 'Upper' o 'Lower', y es el que decide los nombres de la
        boca: 'C_<rig>_<label>Local_OFF' y 'C_<rig>_lip<label>_GRP'.

        Dos enganches, uno por cada espacio en el que vive la boca:
          - LOCAL: el '<label>Local_OFF' pasa a seguir al centro-con-jaw.
            Como 'lip<label>PreBind_JNT' se queda siguiendo al centro limpio,
            esa diferencia es justo lo que deforma: la boca se abre.
          - GLOBAL: el _GRP raiz del control pasa a seguir al equivalente
            global, para que el control acompañe en pantalla.

        Devuelve (driven_local, driven_global).
        """
        center_local = f"C_{self.rig_name}_lipProjected_LOC"
        lip_off = f"C_{self.rig_name}_{label}Local_OFF"
        lip_ctrl = f"C_{self.rig_name}_lip{label}_GRP"

        if not cmds.objExists(center_local):
            cmds.warning(f"[Jaw] No existe '{center_local}'. "
                         "Construye el MouthModule antes que el jaw.")
            return None, None

        delta_node = self._build_jaw_delta_matrix(label, jaw_ctrl, jaw_ctrl_grp)
        if not delta_node:
            return None, None

        # --- LOCAL: el que abre la boca ---
        driven_local = self._build_jaw_driven_locator(
            label=label,
            source_locator=center_local,
            delta_node=delta_node,
            locator_name=f"C_{self.rig_name}_lipProjectedJaw{label}_LOC"
        )
        if driven_local and cmds.objExists(lip_off):
            self._retarget_parent_constraint(lip_off, driven_local)
        elif not cmds.objExists(lip_off):
            cmds.warning(f"[Jaw] No existe '{lip_off}'.")

        # --- GLOBAL: el que arrastra al control en pantalla ---
        driven_global = None
        constrained_grp = self._find_constrained_ancestor(lip_ctrl) if cmds.objExists(lip_ctrl) else None

        if constrained_grp:
            constraint = cmds.listRelatives(constrained_grp, children=True, type="parentConstraint")[0]
            targets = cmds.parentConstraint(constraint, q=True, targetList=True) or []
            # El locator global de la boca lo crea cada lado con su propio
            # prefijo (L_ / R_), asi que el driver real lo saco del constraint
            # que ya existe en vez de adivinar el prefijo.
            source_global = next((t for t in targets if t.endswith("lipProjectedGlobal_LOC")), None)

            if source_global:
                driven_global = self._build_jaw_driven_locator(
                    label=label,
                    source_locator=source_global,
                    delta_node=delta_node,
                    locator_name=f"C_{self.rig_name}_lipProjectedGlobalJaw{label}_LOC"
                )
                if driven_global:
                    self._retarget_parent_constraint(constrained_grp, driven_global)
        else:
            cmds.warning(f"[Jaw] No encuentro el grupo constreñido de '{lip_ctrl}'.")

        return driven_local, driven_global

    # ------------------------------------------------------------------
    # CIERRE DE LA CADENA: TRACKERS + JOINTS FINALES
    # ------------------------------------------------------------------
    def _get_or_create_curve_motion_locator(self, curve_name, base_name, u_value, side=None):
        """
        Crea (una unica vez) un motionPath sobre 'curve_name' fijo en 'u_value'
        con un locator enganchado a su salida.

        Mismo patron que el del modulo de la boca con dos diferencias:
          - fractionMode a 1, asi u_value va de 0 a 1 y no depende del numero
            de spans de la curva (aqui reparto puntos, no coloco uno suelto).
          - no conecto '.rotate': con follow apagado el motionPath saca siempre
            0, y conectarlo solo serviria para bloquear el canal del locator.
        """
        prefix = f"{side}_{self.rig_name}" if side else f"C_{self.rig_name}"
        locator_name = f"{prefix}_{base_name}_tracker_LOC"
        motionpath_name = f"{prefix}_{base_name}_MPA"

        if cmds.objExists(locator_name):
            return motionpath_name, locator_name

        motionpath_node = NodeCreator(
            side=prefix, node_type="motionPath", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        motionpath_node = cmds.rename(motionpath_node, motionpath_name)

        cmds.connectAttr(f"{curve_name}.worldSpace[0]", f"{motionpath_node}.geometryPath")
        cmds.setAttr(f"{motionpath_node}.fractionMode", 1)
        cmds.setAttr(f"{motionpath_node}.uValue", u_value)

        locator_tracker = cmds.spaceLocator(name=locator_name)[0]
        cmds.connectAttr(f"{motionpath_node}.allCoordinates", f"{locator_tracker}.translate")

        return motionpath_node, locator_tracker

    def _build_final_lip_joints(self, pinch_lines, joint_count=7):
        """
        Cierra la cadena de curvas: reparte 'joint_count' trackers a lo largo de
        cada JawPinchLine y cuelga un joint de bind de cada uno.

        Las JawPinchLine son el ultimo eslabon (labios + jaw + comisuras), asi
        que estos joints son los unicos que llevan TODO el movimiento a la malla.
        Tienen que ser joints nuevos: los de la cadena (lipLower_JNT, depresor,
        pinch...) ya deforman su propia curva aguas arriba, y colgarlos de un
        tracker de la curva final montaria un ciclo en el DG.

        El orden de CVs va de comisura a comisura, asi que u=0 cae en el lado L
        y u=1 en el R: el reparto de prefijos sigue ese orden.
        """
        bind_joints = {}

        if joint_count < 3:
            cmds.warning("[Jaw] joint_count minimo 3.")
            return bind_joints

        mid_index = (joint_count - 1) / 2.0

        for label, curve in pinch_lines.items():
            if not cmds.objExists(curve):
                cmds.warning(f"[Jaw] No existe '{curve}'. "
                             "Lanza _build_jaw_pinch_lines antes.")
                continue

            joints = []

            for i in range(joint_count):
                if i < mid_index:
                    side = "L"
                elif i > mid_index:
                    side = "R"
                else:
                    side = "C"

                base_name = f"lip{label}Bind{i:02d}"
                u_value = i / float(joint_count - 1)

                _, tracker = self._get_or_create_curve_motion_locator(
                    curve_name=curve, base_name=base_name, u_value=u_value, side=side
                )

                joint_name = f"{side}_{self.rig_name}_{base_name}_JNT"
                if not cmds.objExists(joint_name):
                    # select(clear) antes de crear: si no, cmds.joint cuelga el
                    # nuevo joint del anterior y sale una cadena en vez de 7
                    # joints sueltos.
                    cmds.select(clear=True)
                    joint = cmds.joint(n=joint_name)
                    cmds.matchTransform(joint, tracker, pos=True, rot=False)
                    cmds.matchTransform(joint, self.jaw_root, rot=True, pos=False)
                    cmds.makeIdentity(joint, apply=True, r=True)
                    cmds.select(clear=True)
                else:
                    joint = joint_name

                # mo=True: el tracker solo tiene traslacion, asi que el joint
                # conserva su orientacion de build y se limita a seguir el
                # punto de la curva. Nada de rotacion del motionPath = nada
                # de flips en las comisuras.
                if not cmds.listRelatives(joint, type="parentConstraint"):
                    cmds.parentConstraint(tracker, joint, mo=True)

                joints.append(joint)

            bind_joints[label] = joints

        return bind_joints

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------
    def build(self):
        """Construye el rig del jaw."""

        base_name = "jaw"

        # 1. POSICIONES REALES DE LAS GUIAS (para joints bind/ik/fk)
        pos_jaw_root = cmds.xform(self.jaw_root, q=True, ws=True, t=True)
        pos_jaw_end = cmds.xform(self.jaw_end,  q=True, ws=True, t=True)
        
        # 2. CREAR JOINTS DE RIG
        cmds.select(clear=True)
        jaw_upper_jnt = cmds.joint(n=f"{self.prefix}_jawUpper_JNT", p=pos_jaw_root)
        cmds.matchTransform(jaw_upper_jnt, self.jaw_root, rot=True, pos=False)
        
        cmds.select(clear=True)
        jaw_lower_jnt = cmds.joint(n=f"{self.prefix}_jawLower_JNT", p=pos_jaw_root)
        cmds.matchTransform(jaw_lower_jnt, self.jaw_root, rot=True, pos=False)
        
        #Controles con el local set up
        #UPPER CONTROL 
        jaw_upper_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=f"{self.prefix}_jawUpper_CTRL"
            )
        
        cmds.addAttr(jaw_upper_ctrl, ln = "extraAttrSep",nn = "EXTRA_ATTR",at = "enum",en = "------" ,k=False)
        cmds.setAttr(f"{jaw_upper_ctrl}.extraAttrSep", cb=True)  
        cmds.setAttr(f"{jaw_upper_ctrl}.extraAttrSep", l=True)
        
        cmds.addAttr(jaw_upper_ctrl, ln = "collision",nn = "Collision",at = "float",k=True, min=0, max=1, dv=0)
        cmds.addAttr(jaw_upper_ctrl, ln = "LUpperLower",nn = "L Jaw Upper <---> Lower",at = "float",k=True, min=0, max=1, dv=1)
        cmds.addAttr(jaw_upper_ctrl, ln = "RUpperLower",nn = "R Jaw Upper <---> Lower",at = "float",k=True, min=0, max=1, dv=1)

        
        
        #UPPER CONTROL GROUP
        jaw_upper_grp = self.group_maker.create_rig_hierarchy(
            jaw_upper_ctrl, self.jaw_root, match_rotation=True, world_space=True
        )
        
        #UPPER CONTROL OFFSET
        self._offset_control_shape(jaw_upper_ctrl, move=(0, 2, 10))
        
        #UPPER CONTROL LOCAL OFF/TRN

        upper_off_name = f"{self.prefix}_jawUpperLocal_OFF"
        upper_trn_name = f"{self.prefix}_jawUpperLocal_TRN"
        if not cmds.objExists(upper_off_name):
            upperJaw_local_off, upperJaw_local_trn = self._build_off_network(
                prefix=self.prefix,
                base_name="jawUpper", source_ctrl=jaw_upper_ctrl, source_ctrl_grp=jaw_upper_grp
            )
        else:
            upperJaw_local_off = upper_off_name
            upperJaw_local_trn = upper_trn_name

        
        #LOWER CONTROL
        jaw_lower_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=f"{self.prefix}_jawLower_CTRL"
            )

        #LOWER CONTROL GROUP
        jaw_lower_grp = self.group_maker.create_rig_hierarchy(
            jaw_lower_ctrl, self.jaw_root, match_rotation=True, world_space=True
        )

        #LOWER CONTROL OFFSET
        self._offset_control_shape(jaw_lower_ctrl, move=(0, -2, 10))
        
        #LOWER CONTROL LOCAL OFF/TRN
        lower_off_name = f"{self.prefix}_jawLowerLocal_OFF"
        lower_trn_name = f"{self.prefix}_jawLowerLocal_TRN"
        if not cmds.objExists(lower_off_name):
            lowerJaw_local_off, lowerJaw_local_trn = self._build_off_network(
                prefix=self.prefix,
                base_name="jawLower", source_ctrl=jaw_lower_ctrl, source_ctrl_grp=jaw_lower_grp
            )
        else:
            lowerJaw_local_off = lower_off_name
            lowerJaw_local_trn = lower_trn_name

        #LOS TRN LOCALES CONDUCEN A SUS JOINTS
        self._constrain_joint_to_local_trn(upperJaw_local_trn, jaw_upper_jnt)
        self._constrain_joint_to_local_trn(lowerJaw_local_trn, jaw_lower_jnt)

        # 3. EXPONER LOS NODOS CLAVE
        # Para que el modulo de la boca (u otros) puedan engancharse sin
        # reconstruir los nombres con f-strings.
        self.jaw_upper_jnt = jaw_upper_jnt
        self.jaw_lower_jnt = jaw_lower_jnt
        self.jaw_upper_ctrl = jaw_upper_ctrl
        self.jaw_lower_ctrl = jaw_lower_ctrl
        self.jaw_upper_local_trn = upperJaw_local_trn
        self.jaw_lower_local_trn = lowerJaw_local_trn

        #CONEXIONES PARA Q EL LOWER EMPUJE AL UPPER
        #ROTACIONES
        
        floatMath_node = NodeCreator(
            side=self.prefix, node_type="floatMath", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        cmds.setAttr(f"{floatMath_node}.operation", 1) #Subtract
        
        # cmds.connectAttr(f"{jaw_lower_ctrl}.rotateX", f"{floatMath_node}.floatA")
        # cmds.connectAttr(f"{jaw_upper_ctrl}.rotateX", f"{floatMath_node}.floatB")
        
        clamp_node = NodeCreator(
            side=self.prefix, node_type="clamp", base_name=base_name,
            name="LocalClamp", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        
        cmds.connectAttr(f"{floatMath_node}.outFloat", f"{clamp_node}.inputR")
        cmds.setAttr(f"{clamp_node}.minR", -360)
        
        floatMath02_node = NodeCreator(
            side=self.prefix, node_type="floatMath", base_name=base_name,
            name="Local02", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        cmds.setAttr(f"{floatMath02_node}.operation", 1) #Subtract
        
        cmds.connectAttr(f"{clamp_node}.outputR", f"{floatMath02_node}.floatA")
        cmds.connectAttr(f"{jaw_upper_ctrl}.collision", f"{floatMath02_node}.floatB")

        # El resultado entra en el SDK del upper.
        # create_rig_hierarchy monta GRP > SPC > OFF > SDK > ANIM pero solo
        # devuelve el GRP, asi que bajamos por la jerarquia a buscar el SDK
        # en vez de reconstruir su nombre con un f-string.
        jaw_upper_sdk = self._get_rig_group(jaw_upper_grp, "SDK")
        if jaw_upper_sdk:
            cmds.connectAttr(f"{floatMath02_node}.outFloat", f"{jaw_upper_sdk}.rotateX")

        #TRANSLACIONES

        # Recuperamos el multMatrix del lower buscandolo por conexion.
        # Funciona igual tanto si acabamos de crear la red como si ya existia
        # de un build anterior (rama idempotente de arriba).
        lower_mult_node = self._get_local_mult_matrix(jaw_lower_ctrl)

        lower_decompose_node = None
        if lower_mult_node:
            lower_decompose_node = NodeCreator(
                side=self.prefix, node_type="decomposeMatrix", base_name="jawLower",
                name="LocalTranslate", tag="CTRL", parent=None, custom_suffix=None
            ).create()

            # matrixSum es un output: puede alimentar varios destinos a la vez,
            # asi que el decompose que ya cuelga de el sigue intacto.
            cmds.connectAttr(
                f"{lower_mult_node}.matrixSum",
                f"{lower_decompose_node}.inputMatrix",
                force=True
            )

            cmds.connectAttr(f"{lower_decompose_node}.outputRotateX", f"{floatMath_node}.floatA")
            
        multMatrix_node = NodeCreator(
            side=self.prefix, node_type="multMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()            
        
        cmds.connectAttr(f"{jaw_upper_ctrl}.matrix", f"{multMatrix_node}.matrixIn[0]")
        
        jaw_upper_anim = self._get_rig_group(jaw_upper_grp, "ANIM")
        if jaw_upper_anim:
            cmds.connectAttr(f"{jaw_upper_anim}.matrix", f"{multMatrix_node}.matrixIn[1]")
            
        
        upper_decompose_node = NodeCreator(
                side=self.prefix, node_type="decomposeMatrix", base_name="jawUpper",
                name="LocalTranslate", tag="CTRL", parent=None, custom_suffix=None
        ).create()     
        
        cmds.connectAttr(f"{multMatrix_node}.matrixSum", f"{upper_decompose_node}.inputMatrix")
        cmds.connectAttr(f"{upper_decompose_node}.outputRotateX", f"{floatMath_node}.floatB")

        # 4. COMISURAS DE LA BOCA
        # El orden importa: los joints tienen que existir antes de que nadie
        # los use como target de un constraint o como influencia de un skin.
        corner_joints = self._create_corner_joints()
        self.corner_joints = corner_joints

        self._constrain_corner_joints(
            corner_joints, jaw_upper_jnt, jaw_lower_jnt, jaw_upper_ctrl
        )

        # 4.5 LOS LABIOS SIGUEN A LA MANDIBULA
        # Antes de las lineas de pinch: estas leen el worldSpace de las curvas
        # de la boca, que ya tienen que venir con la apertura aplicada.
        upper_driven_local, upper_driven_global = self._link_lip_to_jaw(
            "Upper", jaw_upper_ctrl, jaw_upper_grp
        )
        lower_driven_local, lower_driven_global = self._link_lip_to_jaw(
            "Lower", jaw_lower_ctrl, jaw_lower_grp
        )

        # 5. LINEAS DE PINCH DEL JAW
        jaw_pinch_lines = self._build_jaw_pinch_lines()
        jaw_pinch_skins = self._bind_jaw_pinch_lines(corner_joints)

        # 6. JOINTS FINALES SOBRE LAS LINEAS DE PINCH DEL JAW
        lip_bind_joints = self._build_final_lip_joints(jaw_pinch_lines)
        self.lip_bind_joints = lip_bind_joints

        print(f"[Jaw] Upper lip driven: {upper_driven_local} / {upper_driven_global}")
        print(f"[Jaw] Lower lip driven: {lower_driven_local} / {lower_driven_global}")
        print(f"[Jaw] Corner joints: {corner_joints}")
        print(f"[Jaw] Pinch lines:   {jaw_pinch_lines}")
        print(f"[Jaw] Pinch skins:   {jaw_pinch_skins}")
        print(f"[Jaw] Bind joints:   {lip_bind_joints}")

        return jaw_upper_grp, jaw_lower_grp