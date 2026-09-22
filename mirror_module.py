import maya.cmds as cmds


class Mirror(object):
    """
    Mirror de les guies de les potes L -> R.

    Davant:  L_clavicule -> L_clavicule_start
                         -> L_hip -> L_knee -> L_ankle
    Darrere: L_hip_back -> L_knee_back -> L_hock_back -> L_ankle_back
             (sense clavicula: la pelvis es la de l espina)

    Casc (fills del menudillo): ball (amb toe_tip a dins), heel, hoof_in, hoof_out.
    La cadena principal es fa amb mirrorJoint; els joints del casc es tornen
    a crear a ma espellant la X, com abans.
    """

    FOOT_NAMES = ["ball", "toe_tip", "heel", "hoof_in", "hoof_out"]

    def __init__(self, clavicule_guide="L_clavicule",
                 clavicule_guide_back="L_hip_back",
                 foot_joints=None,
                 foot_joints_back=None,
                 rig_name="R_Character"):
        self.clavicule_guide = clavicule_guide
        self.clavicule_guide_back = clavicule_guide_back
        self.foot_joints = foot_joints or []
        self.foot_joints_back = foot_joints_back or []
        self.rig_name = rig_name
        self.r_clavicule_start = None
        self.r_clavicule_start_back = None

    # ------------------------------------------------------------------ #
    # HELPERS
    # ------------------------------------------------------------------ #
    def _foot_list(self, given, suffix):
        """
        Llista de joints del casc: [ball, toe_tip, heel, hoof_in, hoof_out].
        Si la UI passa la llista antiga de 3 (ball, tip, heel), s hi afegeixen
        les vores del casc.
        """
        defaults = [f"L_{n}{suffix}" for n in self.FOOT_NAMES]
        if not given:
            return defaults
        given = list(given)
        for extra in defaults[len(given):]:
            given.append(extra)
        return given

    @staticmethod
    def _to_r(name):
        return name.replace("L_", "R_", 1)

    def _resolve_back_root(self):
        """Compatibilitat: si arriba el nom antic de la clavicula del darrere, fa servir L_hip_back."""
        if cmds.objExists(self.clavicule_guide_back):
            return self.clavicule_guide_back
        if cmds.objExists("L_hip_back"):
            print(f"[Mirror] {self.clavicule_guide_back} no existeix, es fa servir L_hip_back.")
            return "L_hip_back"
        return self.clavicule_guide_back

    # ------------------------------------------------------------------ #
    # MIRROR D UNA CADENA
    # ------------------------------------------------------------------ #
    @staticmethod
    def _chain_root(guide):
        """Puja fins al joint arrel (per si arriba un joint que no es l arrel)."""
        node = guide
        while True:
            parent = cmds.listRelatives(node, parent=True, type="joint")
            if not parent:
                return node
            node = parent[0]

    def _mirror_chain(self, guide, foot_joints, ankle_name):
        if not cmds.objExists(guide):
            cmds.warning(f"No existe: {guide}")
            return None
        guide = self._chain_root(guide)
        if not cmds.objExists(ankle_name):
            cmds.warning(f"No existe: {ankle_name}")
            return None

        ball_jnt, tip_jnt = foot_joints[0], foot_joints[1]
        # tot menys el tip (que va dins del ball) penja directament del menudillo
        root_foot_joints = [j for j in foot_joints if j != tip_jnt and cmds.objExists(j)]

        # 0. Si ja hi ha un R d abans, s esborra per no crear R_xxx1
        r_root_name = self._to_r(guide)
        if cmds.objExists(r_root_name):
            cmds.delete(r_root_name)
            print(f"[Mirror] Esborrat {r_root_name} anterior.")
        for jnt in foot_joints:
            r_old = self._to_r(jnt)
            if cmds.objExists(r_old):
                cmds.delete(r_old)

        # 1. Treu els joints del casc al mon (el tip surt amb el ball)
        for jnt in root_foot_joints:
            cmds.parent(jnt, world=True)

        # 2-3. Treu la cadena del seu grup
        original_parent = cmds.listRelatives(guide, parent=True)
        if original_parent:
            cmds.parent(guide, world=True)

        # 4. Mirror de la cadena principal
        mirrored = cmds.mirrorJoint(
            guide,
            mirrorYZ=True,
            mirrorBehavior=True,
            searchReplace=("L_", "R_")
        )
        r_guide = mirrored[0]

        # 5-6. Torna a posar L on era
        if original_parent:
            cmds.parent(guide, original_parent[0])
        for jnt in root_foot_joints:
            cmds.parent(jnt, ankle_name)

        # 7. Crea el casc R espellant la X
        r_ankle_name = self._to_r(ankle_name)

        def mirrored_pos(jnt):
            p = cmds.xform(jnt, q=True, ws=True, t=True)
            return (-p[0], p[1], p[2])

        # ball + tip (fill del ball)
        cmds.select(clear=True)
        r_ball = cmds.joint(n=self._to_r(ball_jnt), p=mirrored_pos(ball_jnt))
        if cmds.objExists(tip_jnt):
            cmds.joint(n=self._to_r(tip_jnt), p=mirrored_pos(tip_jnt))
        if cmds.objExists(r_ankle_name):
            cmds.parent(r_ball, r_ankle_name)

        # heel, hoof_in, hoof_out: fills directes del menudillo
        for jnt in root_foot_joints:
            if jnt == ball_jnt:
                continue
            cmds.select(clear=True)
            r_jnt = cmds.joint(n=self._to_r(jnt), p=mirrored_pos(jnt))
            if cmds.objExists(r_ankle_name):
                cmds.parent(r_jnt, r_ankle_name)
        cmds.select(clear=True)

        # 8. R al mateix grup que L
        if original_parent:
            cmds.parent(r_guide, original_parent[0])

        print(f"Mirror OK -> {r_guide}")
        return r_guide

    def mirror(self):
        # Pota de davant
        self.r_clavicule_start = self._mirror_chain(
            self.clavicule_guide,
            self._foot_list(self.foot_joints, ""),
            "L_ankle"
        )

        # Pota del darrere (arrel = maluc, sense clavicula)
        self.r_clavicule_start_back = self._mirror_chain(
            self._resolve_back_root(),
            self._foot_list(self.foot_joints_back, "_back"),
            "L_ankle_back"
        )