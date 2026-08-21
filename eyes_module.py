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
                 eye_direct="eye_direct"):
        

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
        self.styles = {"mainFk": "circleControl"}
        
        self.side = side
        self.prefix = f"{self.side}_{rig_name}"

        # Guias que llevan un segundo control (Sub) ademas del principal
        self.sub_control_guides = [
            self.eye_inner_corner,
            self.eye_outer_corner,
            self.eyelid_up,
            self.eyelid_low,
        ]

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
        cmds.connectAttr(f"{decompose_node}.outputTranslate", f"{local_trn}.translate")
        cmds.connectAttr(f"{decompose_node}.outputRotate", f"{local_trn}.rotate")
        cmds.connectAttr(f"{decompose_node}.outputScale", f"{local_trn}.scale")
        cmds.connectAttr(f"{local_trn}.worldMatrix[0]", f"{decompose_trn_node}.inputMatrix")

        return local_off, local_trn

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
                lib_name=self.styles["mainFk"],
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

        # Candidatos: todos los OFF del setup local (principales y Sub)
        candidates = list(self.eye_local_offs.values()) + list(self.eye_sub_local_offs.values())

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
                    lib_name=self.styles["mainFk"],
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
                    lib_name=self.styles["mainFk"],
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

        cmds.select(clear=True)

        return self.joints_group