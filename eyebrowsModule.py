import math
import maya.api.OpenMaya as om2
import maya.cmds as cmds

import controlsLibrary
import groups_module
import guides_module
import rigRoot_module
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator


class EyebrowsModule(object):

    # ------------------------------------------------------------------
    # ESPEJO DEL LADO R
    # ------------------------------------------------------------------
    # Las guias del lado derecho estan en mirror BEHAVIOUR respecto al
    # izquierdo: sus ejes son los del espejo de L pero negados, o sea que la
    # ceja derecha esta girada 180 grados, no reflejada. Esa convencion es la
    # correcta para ROTACIONES (los mismos valores de rotate dan movimientos
    # simetricos) pero es la contraria para TRASLACIONES, y este sistema mueve
    # todo por traslacion: el _REL alimenta el translate del _Local_TRN.
    #
    # OJO, no sirve el truco del modulo de la boca (scaleX = -1 en el _GRP mas
    # una matriz de espejo al final del multMatrix). Alli la cadena sube hasta
    # el _GRP SIN incluirlo, asi que la escala negativa se queda fuera. Aqui
    # generate_relative_control_transform sube hasta top_grp INCLUYENDOLO y
    # ademas hornea la inversa del bind, asi que el espejo se cancela solo:
    #
    #     cadena  = A x M
    #     invBind = (A0 x M)^-1 = M^-1 x A0^-1
    #     delta   = A x M x M^-1 x A0^-1 = A x A0^-1
    #
    # La M desaparece. Por eso hay que corregir el signo DESPUES del
    # decomposeMatrix, que es lo que hace el modulo de los ojos.
    MIRROR_R_TRANSLATION = True
    # Medido, no supuesto: moviendo cada control un paso y comparando el
    # desplazamiento en MUNDO del control con el de su _Local_TRN, la X ya salia
    # acompanando y la Y y la Z al reves. De ahi este triple.
    MIRROR_R_TRANSLATION_SIGN = (-1.0, 1.0, 1.0)

    # Las TANGENTES necesitan el signo contrario, y no es un capricho.
    #
    # Los _GRP de los sub acaban con rotate Z = 180 y scale Z = -1, que no los
    # pone este modulo: los escribe Maya al hacer cmds.parent(sub_ctl_gen,
    # main_ctl) de forma absoluta dentro de un padre con escala negativa. Para
    # conservar la posicion de mundo compensa con un giro de 180 mas una escala
    # negada. Los _GRP de las tangentes no necesitaron esa compensacion y se
    # quedaron limpios (rotate 0, scale 1).
    #
    # Y eso importa porque cada _Local_OFF se matchea con rot=True contra su
    # _GRP, asi que los dos sistemas viven en marcos girados 180 grados el uno
    # respecto del otro. El mismo signo que corrige uno estropea el otro.
    #
    # La solucion limpia seria que ningun _GRP intermedio acabase con esas
    # compensaciones, y entonces bastaria un unico signo para todo el modulo.
    # Mientras tanto, esto.
    # Exactamente el opuesto del de arriba, que es lo que confirma el
    # diagnostico: los dos marcos se diferencian en ese giro de 180 grados.
    MIRROR_R_TANGENT_SIGN = (1.0, -1.0, -1.0)

    # La otra mitad del problema, esta vez del lado del animador.
    #
    # Con lo de arriba el sistema ya se mueve en espejo, pero el gizmo del
    # control sigue en orientacion de behaviour, asi que el control tira hacia
    # un lado y la ceja hacia el otro. Se le voltean los ejes al grupo del
    # control principal, y los sub y las tangentes lo heredan porque cuelgan
    # de el.
    #
    # scale y no rotate a proposito: la shape se dibuja alrededor del origen
    # del grupo, asi que el control no se mueve de sitio, solo cambian las
    # direcciones de sus canales.
    # ------------------------------------------------------------------
    # SLIDE SETUP (deslizamiento sobre la NURBS del craneo)
    # ------------------------------------------------------------------
    # Ejes del aimMatrix, tal como los pide el documento: el primario alineado
    # con la tangente U de la superficie y el secundario con la V.
    SLIDE_PRIMARY_AXIS = (-1.0, 0.0, 0.0)
    SLIDE_SECONDARY_AXIS = (0.0, -1.0, 0.0)
    SLIDE_PRIMARY_MODE = 2      # 2 = align
    SLIDE_SECONDARY_MODE = 2    # 2 = align

    # Fila extra de joints por encima de la ceja, deslizando por la misma NURBS
    # con un desplazamiento en V. Por defecto DESACTIVADO: existe en el grafo de
    # referencia pero no sabemos que comportamiento busca, y esta reconstruido
    # de una captura donde los valores del remapValue no se leian.
    BUILD_FOREHEAD_ROW = False
    FOREHEAD_V_OFFSET = 0.15

    MIRROR_R_CONTROL_AXES = True
    MIRROR_R_CONTROL_SCALE = (-1.0, -1.0, -1.0)

    def __init__(
        self,
        guide_prefix="L_eyebrow_root",
        num_joints=10,
        rig_name="Character",
        side="L",
        root_instance=None,
        **kwargs,
    ):
        self.guide_prefix = guide_prefix
        self.num_joints = num_joints
        self.side = side
        self.rig_name = rig_name
        self.prefix = f"{self.side}_{rig_name}_eyebrow"

        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance
        self.control_style = "circleControl"

        self.main_control_style = kwargs.get(
            "main_control_style", self.control_style
        )
        self.corner_control_style = kwargs.get(
            "corner_control_style", self.control_style
        )
        self.tangent_control_style = kwargs.get(
            "tangent_control_style", self.control_style
        )

        # Parametros configurables de la bezier / upCurve
        self.mid_tangent_scale = kwargs.get("mid_tangent_scale", 0.15)
        self.up_curve_offset = kwargs.get("up_curve_offset", 0.5)

        self.up_curve_normal = kwargs.get("up_curve_normal", (0.0, 0.0, 1.0))

        self.up_curve_aim = kwargs.get("up_curve_aim", (0.0, 1.0, 0.0))

        # Convenció d'eixos per a l'aimConstraint de la cadena de joints.
        # aim_vector: eix que ha d'apuntar cap al SEGÜENT joint de la cadena
        # (la direcció "al llarg" de la corba). up_vector: eix que s'alinea
        # amb el worldUpObject (la upCurve). Per defecte assumim la
        # convenció estàndard de Maya (X al llarg de la cadena, Y com a up);
        # canvia-ho si la teva orientació de guies és diferent.
        self.chain_aim_vector = kwargs.get("chain_aim_vector", (1.0, 0.0, 0.0))
        self.chain_up_vector = kwargs.get("chain_up_vector", (0.0, 1.0, 0.0))

        self.rig_joints = []
        self.controls = []
        self.control_groups = []

        self.module_grp = None
        self.joints_grp = None
        self.controls_grp = None
        self.local_grp = None

        self.local_joints = {}
        self.local_transforms = {}
        self.local_curve = None
        self.local_up_curve = None
        self.up_transforms = []

        # NURBS del craneo por la que deslizan las cejas. La crea el
        # guides_module (EyebrowSkullGuides) y aqui solo se lee, igual que la
        # superficie de la boca en mouthModule.
        self.skull_surface = kwargs.get("skull_surface", "eyebrow_skull_NRB")

        self.slide_projected_joints = []
        # _ENV a los que se les ha aplicado la mezcla del slide.
        self.slide_skin_joints = []
        self.forehead_joints = []

    # ------------------------------------------------------------------
    # Connectors i creadors de transformacions relatives / locals
    # ------------------------------------------------------------------
    def generate_relative_control_transform(
        self, control_name, top_grp, create_transform=True, mirror_sign=None
    ):
        """
        mirror_sign: signo del espejo de traslacion para este control en el lado
        R. Si es None se usa MIRROR_R_TRANSLATION_SIGN. Las tangentes pasan
        MIRROR_R_TANGENT_SIGN, ver el comentario de esa constante.
        """

        base_name = control_name.replace("_CTRL", "").replace("_ctl", "")
        grp = cmds.listRelatives(control_name, parent=True, type="transform")[0]

        # Creacio del nodo multMatrix
        mmtx = cmds.createNode(
            "multMatrix", name=f"{base_name}Local_MTX", ss=True
        )

        # Cerca de la jerarquia fins a top_grp
        hierarchy_transforms = []
        current_node = [control_name]

        while current_node:
            node_name = current_node[0]
            hierarchy_transforms.append(node_name)
            if node_name == top_grp:
                break
            current_node = cmds.listRelatives(
                node_name, parent=True, type="transform"
            )

        matrix_inputs = list(reversed(hierarchy_transforms))

        for i, elem in enumerate(matrix_inputs):
            cmds.connectAttr(
                f"{elem}.matrix", f"{mmtx}.matrixIn[{i}]", force=True
            )

        bind_matrix = cmds.getAttr(f"{mmtx}.matrixSum")
        inv_bind_matrix = om2.MMatrix(bind_matrix).inverse()
        bind_index = len(matrix_inputs)
        cmds.setAttr(
            f"{mmtx}.matrixIn[{bind_index}]",
            list(inv_bind_matrix),
            type="matrix",
        )

        dcm = cmds.createNode(
            "decomposeMatrix", name=f"{base_name}Local_DCM", ss=True
        )
        cmds.connectAttr(f"{mmtx}.matrixSum", f"{dcm}.inputMatrix", force=True)

        if not create_transform:
            return dcm

        relative_trn = cmds.createNode(
            "transform", name=f"{base_name}_REL", ss=True
        )
        cmds.parent(relative_trn, grp, relative=True)

        translate_source = f"{dcm}.outputTranslate"
        if self.side == "R" and self.MIRROR_R_TRANSLATION:
            translate_source = self._build_translation_mirror(
                base_name, dcm, mirror_sign)

        cmds.connectAttr(
            translate_source, f"{relative_trn}.translate", force=True
        )
        for out_attr, in_attr in (
            ("outputRotate", "rotate"),
            ("outputScale", "scale"),
        ):
            cmds.connectAttr(
                f"{dcm}.{out_attr}", f"{relative_trn}.{in_attr}", force=True
            )

        return relative_trn, dcm

    def _build_translation_mirror(self, base_name, dcm, mirror_sign=None):
        """
        Mete un multiplyDivide entre el decomposeMatrix y el _REL para invertir
        el signo de la traslacion en el lado R.

        Solo toca translate: con orientaciones en mirror behaviour las
        rotaciones ya salen simetricas y negarlas las romperia. Ver el
        comentario de MIRROR_R_TRANSLATION arriba de la clase.

        Devuelve el plug que hay que conectar al translate del _REL.
        """
        if mirror_sign is None:
            mirror_sign = self.MIRROR_R_TRANSLATION_SIGN

        node_name = f"{base_name}LocalMirror_MDV"

        if not cmds.objExists(node_name):
            node_name = cmds.createNode("multiplyDivide", name=node_name, ss=True)

        cmds.setAttr(f"{node_name}.operation", 1)  # 1 = multiplicar
        for index, axis in enumerate("XYZ"):
            cmds.setAttr(f"{node_name}.input2{axis}", mirror_sign[index])

        cmds.connectAttr(f"{dcm}.outputTranslate", f"{node_name}.input1",
                         force=True)

        return f"{node_name}.output"

    def _mirror_control_axes(self, main_ctl_gen):
        """
        Voltea los ejes del grupo del control principal en el lado R.

        Solo el principal: los sub cuelgan de main_ctl y las tangentes de su
        sub, asi que heredan el volteo. Si se les pusiera tambien, se
        cancelaria.

        MUY IMPORTANTE el momento en que se llama: tiene que ser ANTES de
        generar las redes de matrices de los sub. generate_relative_control_
        transform hornea la inversa del bind leyendo el matrixSum en ese
        instante, asi que si el volteo llega despues, el bind se calculo sin la
        escala y la cadena viva si la lleva. El delta saldria descuadrado.
        """
        if self.side != "R" or not self.MIRROR_R_CONTROL_AXES:
            return None

        if not main_ctl_gen or not cmds.objExists(main_ctl_gen):
            return None

        for index, axis in enumerate("XYZ"):
            plug = f"{main_ctl_gen}.scale{axis}"
            if cmds.getAttr(plug, lock=True) or cmds.listConnections(
                    plug, source=True, destination=False):
                cmds.warning(f"[EyebrowsModule] '{plug}' esta bloqueado o "
                             "conectado, no se voltea.")
                continue
            cmds.setAttr(plug, self.MIRROR_R_CONTROL_SCALE[index])

        return main_ctl_gen

    def _connect_transform_channels(self, driver_node, driven_node):
        """Connecta Translate, Rotate i Scale d'un nodo/transform a un altre."""
        for attr in ("translate", "rotate", "scale"):
            cmds.connectAttr(
                f"{driver_node}.{attr}", f"{driven_node}.{attr}", force=True
            )

    # ------------------------------------------------------------------
    # Local joint helper
    # ------------------------------------------------------------------
    def _create_local_joint(self, parent_trn, name):
        cmds.select(clear=True)
        jnt = cmds.joint(name=name)
        cmds.parent(jnt, parent_trn, relative=True)
        return jnt

    # ------------------------------------------------------------------
    # Curve helpers
    # ------------------------------------------------------------------
    def _cv_count(self, curve):
        """Nombre real de CVs (spans + degree no es fiable en beziers)."""
        return len(cmds.ls(f"{curve}.cv[*]", flatten=True))

    def _average_cv_position(self, curve):
        """Centroide dels CVs en world space."""
        cvs = cmds.ls(f"{curve}.cv[*]", flatten=True)
        if not cvs:
            return om2.MVector(0.0, 0.0, 0.0)

        total = om2.MVector(0.0, 0.0, 0.0)
        for cv in cvs:
            total += om2.MVector(*cmds.pointPosition(cv, world=True))
        return total / float(len(cvs))

    def _park_curve_in_local_grp(self, curve):
        if not (self.local_grp and cmds.objExists(self.local_grp)):
            return

        cmds.parent(curve, self.local_grp, relative=True)
        cmds.setAttr(f"{curve}.inheritsTransform", 0)

    def _skin_curve_one_to_one(self, curve, cv_weights, skin_name):
        cv_count = self._cv_count(curve)
        if cv_count != len(cv_weights):
            cmds.warning(
                f"{curve} te {cv_count} CVs i se n'esperaven "
                f"{len(cv_weights)}. No es pot fer el skin 1:1; revisa el "
                "subdivisionDensity o la distancia de l'offsetCurve."
            )
            return None

        joints = list(dict.fromkeys(cv_weights.values()))
        skin_cluster = cmds.skinCluster(joints, curve, tsb=True, n=skin_name)[0]

        for cv_index, jnt in cv_weights.items():
            cmds.skinPercent(
                skin_cluster,
                f"{curve}.cv[{cv_index}]",
                transformValue=[(jnt, 1.0)],
            )
        return skin_cluster

    # ------------------------------------------------------------------
    # Bezier curve creation
    # ------------------------------------------------------------------
    def _create_local_bezier_curve(self):
        required_labels = ("In", "InTan", "Mid", "OutTan", "Out")
        if not all(label in self.local_joints for label in required_labels):
            cmds.warning(
                "No es poden trobar tots els joints locals necessaris per crear la bezierCurve."
            )
            return None

        in_jnt = self.local_joints["In"]
        in_tan_jnt = self.local_joints["InTan"]
        mid_jnt = self.local_joints["Mid"]
        out_tan_jnt = self.local_joints["OutTan"]
        out_jnt = self.local_joints["Out"]

        in_pos = cmds.xform(in_jnt, q=True, ws=True, t=True)
        in_tan_pos = cmds.xform(in_tan_jnt, q=True, ws=True, t=True)
        mid_pos = cmds.xform(mid_jnt, q=True, ws=True, t=True)
        out_tan_pos = cmds.xform(out_tan_jnt, q=True, ws=True, t=True)
        out_pos = cmds.xform(out_jnt, q=True, ws=True, t=True)

        tangent_scale = self.mid_tangent_scale
        mid_dir = [out_pos[axis] - in_pos[axis] for axis in range(3)]
        mid_in_tan_pos = [
            mid_pos[axis] - mid_dir[axis] * tangent_scale for axis in range(3)
        ]
        mid_out_tan_pos = [
            mid_pos[axis] + mid_dir[axis] * tangent_scale for axis in range(3)
        ]

        cv_positions = [
            in_pos,
            in_tan_pos,
            mid_in_tan_pos,
            mid_pos,
            mid_out_tan_pos,
            out_tan_pos,
            out_pos,
        ]

        bezier_crv = cmds.curve(
            bezier=True,
            d=3,
            p=cv_positions,
            k=[0, 0, 0, 1, 1, 1, 2, 2, 2],
            n=f"{self.prefix}_local_BZC",
        )

        cv_weights = {
            0: in_jnt,
            1: in_tan_jnt,
            2: mid_jnt,
            3: mid_jnt,
            4: mid_jnt,
            5: out_tan_jnt,
            6: out_jnt,
        }

        up_curve = self._create_local_up_curve(bezier_crv)

        # Skin 1:1 de totes dues (pas 8 de la infografia)
        self._skin_curve_one_to_one(
            bezier_crv, cv_weights, f"{self.prefix}_local_curve_SKIN"
        )
        if up_curve:
            self._skin_curve_one_to_one(
                up_curve, cv_weights, f"{self.prefix}_local_upCurve_SKIN"
            )

        self.local_curve = bezier_crv
        return bezier_crv

    # ------------------------------------------------------------------
    # Up curve (offsetCurve directe sobre un duplicat net de la bezier)
    # ------------------------------------------------------------------
    def _create_local_up_curve(self, source_curve):

        # 1) Duplicat net. Conservem la forma bezier (mateixos CVs i mateixos
        #    anchor presets) i eliminem qualsevol historial heretat.
        tmp_crv = cmds.duplicate(
            source_curve, name=f"{self.prefix}_upCRV_src_TMP"
        )[0]
        cmds.delete(tmp_crv, ch=True)

        src_center = self._average_cv_position(tmp_crv)

        def _build_offset(distance, node_name):
            result = cmds.offsetCurve(
                tmp_crv,
                ch=False,
                rn=False,
                cb=2,
                cl=True,
                cr=0.0,
                d=distance,
                tol=0.01,
                sd=0,
                ugn=True,
                normal=self.up_curve_normal,
                name=node_name,
            )
            return result[0] if isinstance(result, list) else result

        # 2) Primer intent amb distancia positiva
        up_curve = _build_offset(
            self.up_curve_offset, f"{self.prefix}_localUp_BZC"
        )

        delta = self._average_cv_position(up_curve) - src_center
        aim = om2.MVector(*self.up_curve_aim)

        if delta.length() > 1e-6 and aim.length() > 1e-6:
            if (delta.normal() * aim.normal()) < 0.0:
                cmds.delete(up_curve)
                up_curve = _build_offset(
                    -self.up_curve_offset, f"{self.prefix}_localUp_BZC"
                )
                delta = self._average_cv_position(up_curve) - src_center

        # 4) Avis si l'offset no ha anat majoritariament cap a l'eix esperat.
        #    Normalment vol dir que up_curve_normal no es perpendicular a la
        #    direccio desitjada.
        if delta.length() > 1e-6 and aim.length() > 1e-6:
            alignment = delta.normal() * aim.normal()
            if alignment < 0.5:
                cmds.warning(
                    f"{up_curve}: l'offset nomes esta alineat un "
                    f"{alignment:.2f} amb up_curve_aim {self.up_curve_aim}. "
                    f"Revisa up_curve_normal (ara {self.up_curve_normal}): ha "
                    "de ser perpendicular a la direccio que vols."
                )

        # 5) Neteja del duplicat temporal
        if cmds.objExists(tmp_crv):
            cmds.delete(tmp_crv)

        self.local_up_curve = up_curve
        return up_curve

    # ------------------------------------------------------------------
    # Motion paths i configuració d'aim
    # ------------------------------------------------------------------
    def _setup_motion_paths_and_aims(self):
        """Pas 9: crea els joints "driven" a la bezierCurve i els up
        transforms a la upCurve amb motionPath, i orienta els joints.

        - TOTS els up_trn només tenen un motionPath (translate). Res més.
        - El PRIMER joint (índex 0) no té "joint anterior" per fer servir
          com a worldUpObject d'un aimConstraint, així que es resol amb
          matrius: es compon la seva pròpia posició (composeMatrix des
          del seu propi motionPath) i s'orienta cap al seu up_trn amb un
          aimMatrix; el resultat es connecta directament a
          offsetParentMatrix (el joint no fa servir translate/rotate).
        - La RESTA de joints reben la posició directament del seu
          motionPath (translate) i s'orienten amb un aimConstraint clàssic
          cap al seu up_trn, fent servir el SEGÜENT joint de la cadena com
          a worldUpObject (l'anterior pel darrer, que no en té de
          següent).
        """
        if not (self.local_curve and self.local_up_curve and self.rig_joints):
            return

        curve_shape = cmds.listRelatives(self.local_curve, shapes=True)[0]
        up_curve_shape = cmds.listRelatives(self.local_up_curve, shapes=True)[0]

        num_jnts = len(self.rig_joints)
        up_transforms = []
        curve_mp_nodes = []

        # 1) MotionPaths: creem els de la bezierCurve (els guardem sense
        #    connectar encara, els necessitem crus pel cas especial del
        #    primer joint) i els de la upCurve, que SEMPRE alimenten
        #    únicament el translate del seu up_trn.
        for i in range(num_jnts):
            idx_str = f"{i + 1:02d}"
            u_val = float(i) / float(num_jnts - 1) if num_jnts > 1 else 0.0

            mp_node = cmds.createNode(
                "motionPath", name=f"{self.prefix}_{idx_str}_MPA", ss=True
            )
            cmds.connectAttr(
                f"{curve_shape}.worldSpace[0]", f"{mp_node}.geometryPath", f=True
            )
            cmds.setAttr(f"{mp_node}.fractionMode", True)
            cmds.setAttr(f"{mp_node}.uValue", u_val)
            curve_mp_nodes.append(mp_node)

            up_mp_node = cmds.createNode(
                "motionPath", name=f"{self.prefix}_{idx_str}_up_MPA", ss=True
            )
            cmds.connectAttr(
                f"{up_curve_shape}.worldSpace[0]", f"{up_mp_node}.geometryPath", f=True
            )
            cmds.setAttr(f"{up_mp_node}.fractionMode", True)
            cmds.setAttr(f"{up_mp_node}.uValue", u_val)

            up_trn = cmds.createNode(
                "transform", name=f"{self.prefix}_{idx_str}_up_TRN", ss=True
            )
            cmds.connectAttr(
                f"{up_mp_node}.allCoordinates", f"{up_trn}.translate", f=True
            )
            up_transforms.append(up_trn)

        self.up_transforms = up_transforms

        # 2) Primer joint (índex 0): composeMatrix (posició pròpia) +
        #    aimMatrix (orientat cap al seu up_trn) -> offsetParentMatrix.
        first_jnt = self.rig_joints[0]
        idx0_str = "01"

        pos_cmm = cmds.createNode(
            "composeMatrix", name=f"{self.prefix}_{idx0_str}Pos_CMM", ss=True
        )
        cmds.connectAttr(
            f"{curve_mp_nodes[0]}.allCoordinates",
            f"{pos_cmm}.inputTranslate",
            force=True,
        )

        aim_cmm = cmds.createNode(
            "composeMatrix", name=f"{self.prefix}_{idx0_str}Aim_CMM", ss=True
        )
        cmds.connectAttr(
            f"{up_transforms[0]}.translate", f"{aim_cmm}.inputTranslate", force=True
        )

        amt = cmds.createNode(
            "aimMatrix", name=f"{self.prefix}_{idx0_str}_AMT", ss=True
        )
        cmds.connectAttr(
            f"{pos_cmm}.outputMatrix", f"{amt}.inputMatrix", force=True
        )
        cmds.connectAttr(
            f"{aim_cmm}.outputMatrix", f"{amt}.primaryTargetMatrix", force=True
        )
        cmds.setAttr(
            f"{amt}.primaryInputAxis", *self.chain_aim_vector, type="double3"
        )
        cmds.setAttr(f"{amt}.primaryMode", 1)  # 1 = Align

        cmds.connectAttr(
            f"{amt}.outputMatrix", f"{first_jnt}.offsetParentMatrix", force=True
        )

        # 3) Segon joint (índex 1): l'ÚNIC que fa servir aimConstraint,
        #    cap al seu up_trn, amb el joint SEGÜENT (índex 2) com a
        #    worldUpObject.
        if num_jnts > 1:
            second_jnt = self.rig_joints[1]
            second_mp_node = curve_mp_nodes[1]
            second_up_trn = up_transforms[1]

            cmds.connectAttr(
                f"{second_mp_node}.allCoordinates",
                f"{second_jnt}.translate",
                force=True,
            )

            up_object = self.rig_joints[2] if num_jnts > 2 else self.rig_joints[0]

            cmds.aimConstraint(
                second_up_trn,
                second_jnt,
                aimVector=self.chain_aim_vector,
                upVector=self.chain_up_vector,
                worldUpType="object",
                worldUpObject=up_object,
                mo=False,
            )

        # 4) Resta de joints (índex 2 en endavant): NOMÉS motionPath
        #    (translate). Cap orientació, cap node addicional.
        for i in range(2, num_jnts):
            jnt = self.rig_joints[i]
            mp_node = curve_mp_nodes[i]

            cmds.connectAttr(
                f"{mp_node}.allCoordinates", f"{jnt}.translate", force=True
            )

    # ------------------------------------------------------------------
    # Organitzacio de l'outliner
    # ------------------------------------------------------------------
    def _ensure_group(self, group_name, parent=None):
        """Crea el grupo si no existe, y lo reemparenta si hace falta."""
        if not cmds.objExists(group_name):
            group_node = cmds.group(em=True, n=group_name)
        else:
            group_node = group_name

        if parent and cmds.objExists(parent):
            current = cmds.listRelatives(group_node, parent=True) or []
            if not current or current[0] != parent:
                cmds.parent(group_node, parent)

        return group_node

    def _park_node(self, node_name, destination):
        """
        Mete un nodo en su grupo, solo si todavia cuelga de la raiz del mundo.

        relative = True porque los grupos de destino estan en identidad, asi que
        conservar los valores locales conserva la matriz mundial. Y ademas evita
        que Maya intente escribir en canales que puedan estar conectados, que
        aqui los hay a patadas: motionPath, offsetParentMatrix, decompose.
        """
        if not node_name or not cmds.objExists(node_name):
            return False
        if cmds.listRelatives(node_name, parent=True):
            return False

        cmds.parent(node_name, destination, relative=True)
        return True

    def _face_systems_root(self):
        """C_<rig>_face_GRP, bajo el rig_GRP. Compartido con boca, jaw y ojos."""
        rig_grp = f"{self.rig_name}_rig_GRP"
        if self.root_instance is not None and hasattr(self.root_instance, "get_rig_grp"):
            rig_grp = self.root_instance.get_rig_grp()

        parent = rig_grp if cmds.objExists(rig_grp) else None
        return self._ensure_group(f"C_{self.rig_name}_face_GRP", parent)

    def _face_controls_root(self):
        """
        C_<rig>_faceControls_GRP, bajo el local_CTL.

        Es el mismo grupo que usan la boca, el jaw y los ojos, y el que lleva el
        parentConstraint desde el head_CTRL. Colgando aqui, los controles de
        ceja siguen a la cabeza sin constraint propio y sin que ese movimiento
        llegue a los joints, que es lo que rompia la blendShape en los otros
        modulos.
        """
        local_ctl = f"{self.rig_name}_local_CTL"
        if self.root_instance is not None:
            local_ctl = getattr(self.root_instance, "localCtl", None) or local_ctl

        parent = local_ctl if cmds.objExists(local_ctl) else None
        return self._ensure_group(f"C_{self.rig_name}_faceControls_GRP", parent)

    def _organize_outliner(self):
        """
        Reparte todo lo que el build deja suelto en la raiz del mundo.

            C_<rig>_face_GRP                  (sistemas, bajo rig_GRP)
               |- <prefix>_systems_GRP
                    |- <prefix>_joints_GRP    bind, projected y forehead
                    |- <prefix>_local_GRP     MainLocal_OFF y las curvas
                    |- <prefix>_rel_GRP       los _REL
                    |- <prefix>_up_GRP        los transforms de la upCurve

            C_<rig>_faceControls_GRP          (controles, bajo local_CTL)
               |- <prefix>_main_ctrl_GRP

        Va al final del build, cuando ya existe todo. Es idempotente.
        """
        systems_grp = self._ensure_group(f"{self.prefix}_systems_GRP",
                                         self._face_systems_root())

        joints_grp = self._ensure_group(f"{self.prefix}_joints_GRP", systems_grp)
        local_grp = self._ensure_group(f"{self.prefix}_local_GRP", systems_grp)
        rel_grp = self._ensure_group(f"{self.prefix}_rel_GRP", systems_grp)
        up_grp = self._ensure_group(f"{self.prefix}_up_GRP", systems_grp)

        self.module_grp = systems_grp
        self.joints_grp = joints_grp

        for joint in (list(self.rig_joints)
                      + list(self.slide_projected_joints)
                      + list(self.forehead_joints)):
            self._park_node(joint, joints_grp)

        # El MainLocal_OFF arrastra toda la jerarquia local: los OFF y TRN de
        # cada sub y de cada tangente cuelgan de el.
        self._park_node(self.local_grp, local_grp)
        self._park_node(self.local_curve, local_grp)
        self._park_node(self.local_up_curve, local_grp)

        for rel_node in cmds.ls(f"{self.prefix}_*_REL", type="transform") or []:
            self._park_node(rel_node, rel_grp)

        for up_trn in self.up_transforms:
            self._park_node(up_trn, up_grp)

        # Los controles van al grupo compartido de la cara, que es el que sigue
        # a la cabeza. Aqui si se reemparenta aunque ya tenga padre.
        controls_root = self._face_controls_root()
        if self.controls_grp and cmds.objExists(self.controls_grp):
            current = cmds.listRelatives(self.controls_grp, parent=True) or []
            if not current or current[0] != controls_root:
                cmds.parent(self.controls_grp, controls_root)

        return systems_grp

    # ------------------------------------------------------------------
    # Slide setup sobre la NURBS del craneo
    # ------------------------------------------------------------------
    def _build_slide_setup(self):
        """
        Proyecta cada joint de la ceja sobre la NURBS del craneo y mezcla entre
        las dos poses con el atributo slide.

            NRB.worldSpace -> closestPointOnSurface.inputSurface
                           -> pointOnSurfaceInfo.inputSurface
            joint.translate -> CPS.inPosition
            CPS.parameterU/V -> POSI.parameterU/V
            POSI.position -> composeMatrix.inputTranslate
            composeMatrix -> aimMatrix.inputMatrix
            POSI.normalizedTangentU -> aimMatrix.primaryTargetVector
            POSI.normalizedTangentV -> aimMatrix.secondaryTargetVector
            aimMatrix.outputMatrix -> Projected_JNT.offsetParentMatrix

        La mezcla se aplica sobre el _ENV que crea el SkinningModule, no sobre
        el _bind_JNT: ese ya tiene el translate conectado al motionPath y un
        constraint pelearia con el. Ver apply_slide_to_env.
        """
        if not self.skull_surface or not cmds.objExists(self.skull_surface):
            cmds.warning(f"[EyebrowsModule] No existe la superficie "
                         f"'{self.skull_surface}', no se monta el slide setup.")
            return []

        if not self.rig_joints:
            return []

        shape = self.skull_surface
        if cmds.nodeType(shape) == "transform":
            shapes = cmds.listRelatives(shape, s=True, ni=True, type="nurbsSurface")
            if not shapes:
                cmds.warning(f"[EyebrowsModule] '{self.skull_surface}' no tiene "
                             "shape de nurbsSurface.")
                return []
            shape = shapes[0]

        for index, driven_joint in enumerate(self.rig_joints):
            base = f"{self.prefix}_{index + 1:02d}"

            cps = self._ensure_node("closestPointOnSurface", f"{base}Slide_CPS")
            posi = self._ensure_node("pointOnSurfaceInfo", f"{base}Slide_POSI")
            cmx = self._ensure_node("composeMatrix", f"{base}Slide_CMM")
            amx = self._ensure_node("aimMatrix", f"{base}Slide_AMT")

            cmds.connectAttr(f"{shape}.worldSpace[0]", f"{cps}.inputSurface", f=True)
            cmds.connectAttr(f"{shape}.worldSpace[0]", f"{posi}.inputSurface", f=True)
            cmds.connectAttr(f"{driven_joint}.translate", f"{cps}.inPosition", f=True)
            cmds.connectAttr(f"{cps}.parameterU", f"{posi}.parameterU", f=True)
            cmds.connectAttr(f"{cps}.parameterV", f"{posi}.parameterV", f=True)
            cmds.connectAttr(f"{posi}.position", f"{cmx}.inputTranslate", f=True)

            cmds.connectAttr(f"{cmx}.outputMatrix", f"{amx}.inputMatrix", f=True)
            cmds.connectAttr(f"{posi}.normalizedTangentU",
                             f"{amx}.primaryTargetVector", f=True)
            cmds.connectAttr(f"{posi}.normalizedTangentV",
                             f"{amx}.secondaryTargetVector", f=True)

            cmds.setAttr(f"{amx}.primaryInputAxis", *self.SLIDE_PRIMARY_AXIS)
            cmds.setAttr(f"{amx}.secondaryInputAxis", *self.SLIDE_SECONDARY_AXIS)
            cmds.setAttr(f"{amx}.primaryMode", self.SLIDE_PRIMARY_MODE)
            cmds.setAttr(f"{amx}.secondaryMode", self.SLIDE_SECONDARY_MODE)

            projected = f"{base}Projected_JNT"
            if not cmds.objExists(projected):
                cmds.select(clear=True)
                projected = cmds.joint(name=projected)
                cmds.setAttr(f"{projected}.inheritsTransform", 0)
            cmds.connectAttr(f"{amx}.outputMatrix",
                             f"{projected}.offsetParentMatrix", f=True)

            if projected not in self.slide_projected_joints:
                self.slide_projected_joints.append(projected)

            if self.BUILD_FOREHEAD_ROW:
                self._build_forehead_row_joint(base, shape, cps)

        self.apply_slide_to_env()
        return self.slide_projected_joints

    def apply_slide_to_env(self):
        """
        Mezcla cada _ENV entre su joint conducido y su joint proyectado.

        El _ENV lo crea el SkinningModule duplicando el _bind_JNT y poniendole
        un parentConstraint de un solo target. Aqui se sustituye por uno de dos,
        con el slide pesando el proyectado y su reverse el conducido: a 0 la
        ceja va libre y a 1 va pegada al craneo.

        ORDEN: necesita que el SkinningModule ya haya corrido. El build de cejas
        va antes, asi que la primera pasada solo avisara. Vuelve a llamarlo
        despues del skinning:

            eyebrows.apply_slide_to_env()

        Es idempotente.
        """
        main_ctl = f"{self.prefix}_Main_CTRL"
        reverse_node = None

        if cmds.objExists(main_ctl) and cmds.attributeQuery(
                "slide", node=main_ctl, exists=True):
            reverse_name = f"{self.prefix}_slide_REV"
            if cmds.objExists(reverse_name):
                reverse_node = reverse_name
            else:
                reverse_node = cmds.createNode("reverse", name=reverse_name, ss=True)
                cmds.connectAttr(f"{main_ctl}.slide", f"{reverse_node}.inputX")
        else:
            cmds.warning(f"[EyebrowsModule] '{main_ctl}.slide' no existe; el "
                         "slide se queda sin conectar.")

        done = []
        missing = []

        for index, driven_joint in enumerate(self.rig_joints):
            projected = f"{self.prefix}_{index + 1:02d}Projected_JNT"
            env_joint = driven_joint.replace("_bind_JNT", "_ENV")

            if not cmds.objExists(env_joint) or not cmds.objExists(projected):
                missing.append(env_joint)
                continue

            old = cmds.listRelatives(env_joint, c=True, type="parentConstraint") or []
            if old:
                cmds.delete(old)

            constraint = cmds.parentConstraint(
                driven_joint, projected, env_joint, mo=True
            )[0]

            if reverse_node:
                weights = cmds.parentConstraint(constraint, q=True, wal=True)
                # weights[0] = el conducido, weights[1] = el proyectado.
                cmds.connectAttr(f"{reverse_node}.outputX",
                                 f"{constraint}.{weights[0]}", f=True)
                cmds.connectAttr(f"{main_ctl}.slide",
                                 f"{constraint}.{weights[1]}", f=True)

            done.append(env_joint)

        if missing:
            cmds.warning(f"[EyebrowsModule] {len(missing)} _ENV sin montar "
                         "(todavia no ha corrido el SkinningModule). Vuelve a "
                         "llamar a apply_slide_to_env() despues del skinning.")

        self.slide_skin_joints = done
        return done

    def _build_forehead_row_joint(self, base, shape, cps):
        """
        Joint extra por encima de la ceja, sobre la misma NURBS.

        Reutiliza la U que ya calculo el closestPointOnSurface del joint de la
        ceja y le suma un offset en V, asi que queda justo encima y acompaña el
        deslizamiento.

        AVISO: reconstruido a partir de una captura del grafo, no de una
        especificacion. La forma general esta clara, los valores concretos no.
        """
        posi = self._ensure_node("pointOnSurfaceInfo", f"{base}Forehead_POSI")
        offset = self._ensure_node("floatMath", f"{base}ForeheadOffset_FLM")

        cmds.setAttr(f"{offset}.operation", 0)  # 0 = sumar
        cmds.connectAttr(f"{cps}.parameterV", f"{offset}.floatA", f=True)
        cmds.setAttr(f"{offset}.floatB", self.FOREHEAD_V_OFFSET)

        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{posi}.inputSurface", f=True)
        cmds.connectAttr(f"{cps}.parameterU", f"{posi}.parameterU", f=True)
        cmds.connectAttr(f"{offset}.outFloat", f"{posi}.parameterV", f=True)

        joint_name = f"{base}Forehead_JNT"
        if not cmds.objExists(joint_name):
            cmds.select(clear=True)
            joint_name = cmds.joint(name=joint_name)
            cmds.setAttr(f"{joint_name}.inheritsTransform", 0)

        cmds.connectAttr(f"{posi}.position", f"{joint_name}.translate", f=True)

        if joint_name not in self.forehead_joints:
            self.forehead_joints.append(joint_name)
        return joint_name

    @staticmethod
    def _ensure_node(node_type, node_name):
        """Crea el nodo si no existe, y si existe lo reutiliza."""
        if cmds.objExists(node_name):
            return node_name
        return cmds.createNode(node_type, name=node_name, ss=True)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self):
        base_prefix = self.guide_prefix.replace("L_", "").replace("R_", "")

        # 1) JOINTS
        created_joints = []
        for i in range(1, self.num_joints + 1):
            guide_name = f"{self.side}_{base_prefix}_{i:02d}"

            if cmds.objExists(guide_name):
                pos = cmds.xform(guide_name, q=True, ws=True, t=True)
                rot = cmds.xform(guide_name, q=True, ws=True, ro=True)

                cmds.select(clear=True)
                jnt_name = f"{self.prefix}_{i:02d}_bind_JNT"
                jnt = cmds.joint(name=jnt_name, p=pos)
                cmds.setAttr(f"{jnt}.rotate", *rot)
                created_joints.append(jnt)
            else:
                cmds.warning(f"No s'ha trobat la guia: {guide_name}")

        self.rig_joints = created_joints

        if not created_joints:
            return

        # 2) MAIN CONTROL
        main_ctl_grp = cmds.group(em=True, n=f"{self.prefix}_main_ctrl_GRP")
        self.controls_grp = main_ctl_grp

        mid_idx = max(1, math.ceil(self.num_joints / 2.0))
        mid_guide_name = f"{self.side}_{base_prefix}_{mid_idx:02d}"

        main_ctl = controlsLibrary.create_control_from_lib(
            lib_name=self.main_control_style,
            final_name=f"{self.prefix}_Main_CTRL",
        )
        main_ctl_gen = self.group_maker.create_rig_hierarchy(
            main_ctl, mid_guide_name
        )
        cmds.parent(main_ctl_gen, main_ctl_grp)

        # Volteo de ejes del lado R. Va aqui, antes de que se genere ninguna
        # red de matrices, porque esas redes hornean la inversa del bind.
        self._mirror_control_axes(main_ctl_gen)

        if not cmds.attributeQuery("slide", node=main_ctl, exists=True):
            cmds.addAttr(
                main_ctl,
                longName="slide",
                attributeType="float",
                defaultValue=1.0,
                minValue=0.0,
                maxValue=1.0,
                keyable=True,
            )

        self.controls.append(main_ctl)
        self.control_groups.append(main_ctl_gen)

        # 3) LOCAL MAIN GROUP
        main_local_off = cmds.group(em=True, n=f"{self.prefix}MainLocal_OFF")
        cmds.matchTransform(main_local_off, main_ctl_gen, pos=True, rot=True)

        main_local_trn = cmds.group(
            em=True, n=f"{self.prefix}MainLocal_TRN", p=main_local_off
        )
        self.local_grp = main_local_off
        self.local_transforms["Main"] = main_local_trn

        # 4) CONTROLS SECUNDARIS
        sub_indices = {
            "In": 1,
            "Mid": mid_idx,
            "Out": self.num_joints,
        }
        corner_labels = ("In", "Out")

        for label, idx in sub_indices.items():
            sub_guide_name = f"{self.side}_{base_prefix}_{idx:02d}"
            if not cmds.objExists(sub_guide_name):
                cmds.warning(f"No s'ha trobat la guia: {sub_guide_name}")
                continue

            sub_ctrl_name = f"{self.prefix}_{label}_CTRL"
            sub_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.corner_control_style, final_name=sub_ctrl_name
            )
            sub_ctl_gen = self.group_maker.create_rig_hierarchy(
                sub_ctrl, sub_guide_name
            )
            cmds.parent(sub_ctl_gen, main_ctl)

            # Generacio del grup REL i la xarxa de matrius
            rel_grp, _ = self.generate_relative_control_transform(
                control_name=sub_ctrl,
                top_grp=main_ctl_grp,
                create_transform=True,
            )

            self.controls.append(sub_ctrl)
            self.control_groups.append(sub_ctl_gen)

            # Estructura de grups Locals (OFF + TRN)
            local_off = cmds.group(
                em=True, n=f"{self.prefix}{label}Local_OFF", p=main_local_trn
            )
            cmds.matchTransform(local_off, sub_ctl_gen, pos=True, rot=True)

            local_trn = cmds.group(
                em=True, n=f"{self.prefix}{label}Local_TRN", p=local_off
            )
            self.local_transforms[label] = local_trn

            # Connexio des del REL cap al TRN (Mantenint TRN a 0, 0, 0)
            self._connect_transform_channels(rel_grp, local_trn)

            local_jnt = self._create_local_joint(
                local_trn, f"{self.prefix}{label}Local_JNT"
            )
            self.local_joints[label] = local_jnt

            # Controls de tangent per a les cantonades
            if label in corner_labels:
                neighbour_idx = 2 if label == "In" else self.num_joints - 1
                neighbour_guide = (
                    f"{self.side}_{base_prefix}_{neighbour_idx:02d}"
                )

                sub_pos = cmds.xform(sub_guide_name, q=True, ws=True, t=True)
                if cmds.objExists(neighbour_guide):
                    nb_pos = cmds.xform(
                        neighbour_guide, q=True, ws=True, t=True
                    )
                else:
                    nb_pos = sub_pos

                tangent_factor = 0.3
                tangent_pos = [
                    sub_pos[0] + (nb_pos[0] - sub_pos[0]) * tangent_factor,
                    sub_pos[1] + (nb_pos[1] - sub_pos[1]) * tangent_factor,
                    sub_pos[2] + (nb_pos[2] - sub_pos[2]) * tangent_factor,
                ]

                tangent_ctl_name = f"{self.prefix}_{label}Tan_CTRL"
                tangent_ctl = controlsLibrary.create_control_from_lib(
                    lib_name=self.tangent_control_style,
                    final_name=tangent_ctl_name,
                )

                tangent_ctl_gen = self.group_maker.create_rig_hierarchy(
                    tangent_ctl, sub_guide_name
                )
                cmds.xform(tangent_ctl_gen, ws=True, t=tangent_pos)
                cmds.parent(tangent_ctl_gen, sub_ctrl)

                # Creador de matriu i grup REL per a la tangent
                # Aplanem la jerarquia mirant a main_ctl_grp per evitar doble transformació
                tan_rel_grp, _ = self.generate_relative_control_transform(
                    control_name=tangent_ctl,
                    top_grp=main_ctl_grp,
                    create_transform=True,
                    mirror_sign=self.MIRROR_R_TANGENT_SIGN,
                )

                self.controls.append(tangent_ctl)
                self.control_groups.append(tangent_ctl_gen)

                tan_label = f"{label}Tan"

                # Emparentem l'OFF de la tangent directament a main_local_trn
                tan_local_off = cmds.group(
                    em=True,
                    n=f"{self.prefix}{tan_label}Local_OFF",
                    p=main_local_trn,
                )
                cmds.matchTransform(
                    tan_local_off, tangent_ctl_gen, pos=True, rot=True
                )

                tan_local_trn = cmds.group(
                    em=True, n=f"{self.prefix}{tan_label}Local_TRN", p=tan_local_off
                )
                self.local_transforms[tan_label] = tan_local_trn

                # Connexio del REL de la tangent al seu respectiu TRN
                self._connect_transform_channels(tan_rel_grp, tan_local_trn)

                tan_local_jnt = self._create_local_joint(
                    tan_local_trn, f"{self.prefix}{tan_label}Local_JNT"
                )
                self.local_joints[tan_label] = tan_local_jnt

        # 5) BEZIER CURVE + UP CURVE
        self._create_local_bezier_curve()

        # 6) MOTION PATHS + AIM CONSTRAINTS
        self._setup_motion_paths_and_aims()

        # 7) SLIDE SETUP SOBRE LA NURBS DEL CRANEO
        #    Al final: necesita los joints ya conducidos por el motionPath.
        self._build_slide_setup()

        # 8) OUTLINER
        self._organize_outliner()