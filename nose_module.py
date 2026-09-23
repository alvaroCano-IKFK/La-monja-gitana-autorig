import maya.cmds as cmds
import controlsLibrary
import groups_module
import module_specs


class NoseModule(module_specs.FeaturesMixin):
    """
    Modul del nas.

    Una UNICA instancia construeix les DOS aletes (nostrils), igual que la
    boca: guides_module.NoseGuides nomes crea la guia de l'aleta al costat
    +X ("L_nose_nostril"). Aquest modul llegeix aquesta guia i en treu el
    costat R invertint la X ell mateix -- no cal passar per MIRROR ni tenir
    cap guia "R_nose_nostril" a l'escena.

    IMPORTANT: la signatura ha de coincidir amb com el crida build_module.py
    (_build_nose):

        nose_module.NoseModule(
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
            features=features,
        )

    No rep "side": build_module no en passa cap per aquest modul (com la
    boca), perque una sola crida ja fa els dos costats.

    Els controls es creen amb controlsLibrary i despres passen per
    groups_module.ControlsGroups.create_rig_hierarchy(), que els monta la
    jerarquia GRP > SPC > OFF > SDK > ANIM > CTRL y coloca el GRP sobre el
    objetivo. Igual que la resta de moduls de cara.

    El nostril R no te guia real, pero si te JOINT: create_nose_joints() ja
    l'ha creat negant la X de la guia L. Per aixo la jerarquia s'alinea contra
    els JOINTS i no contra les guies: aixi els dos costats van pel mateix
    cami i no cal cap cas especial per la R.
    """

    def __init__(self, rig_name="rig", root_instance=None, features=None):
        self._init_features("nose", features)

        self.rig_name = rig_name
        self.root_instance = root_instance
        self.center_prefix = f"C_{self.rig_name}_"

        # Noms de les guies TAL COM les crea guides_module.NoseGuides.
        # Cap guia de tot el rig porta sufix "_GUIDE". "L_nose_nostrilBase"
        # es de centre (X=0) malgrat el prefix "L_" del nom; "L_nose_nostril"
        # si que es lateral (X>0) i es l'unica guia real de l'aleta.
        self.nose_root_guide = "nose_root"
        self.nose_tip_guide = "nose_tip"
        self.base_nostril_guide = "L_nose_nostrilBase"
        self.nostril_guide = "L_nose_nostril"

        # Noms dels joints definitius
        self.nose_root_jnt = f"{self.center_prefix}noseRoot_JNT"
        self.nose_tip_jnt = f"{self.center_prefix}noseTip_JNT"
        self.base_nostril_jnt = f"{self.center_prefix}nostrilBase_JNT"
        self.nostril_jnt = {
            "L": f"L_{self.rig_name}_nostril_JNT",
            "R": f"R_{self.rig_name}_nostril_JNT",
        }
        self.nostril_jnt_dup = {
            "L": f"L_{self.rig_name}_nostril_dup_JNT",
            "R": f"R_{self.rig_name}_nostril_dup_JNT",
        }

        # Controladors: un nostril_CTRL per costat, un base_nostril_CTRL i
        # nose_root/nose_tip_CTRL unics de centre.
        self.nostril_ctrl = {
            "L": f"L_{self.rig_name}_nostril_CTRL",
            "R": f"R_{self.rig_name}_nostril_CTRL",
        }
        self.base_nostril_ctrl = f"{self.center_prefix}nostrilBase_CTRL"
        self.nose_root_ctrl = f"{self.center_prefix}noseRoot_CTRL"
        self.nose_tip_ctrl = f"{self.center_prefix}noseTip_CTRL"

        self.joints = []
        self.controls = []

        self.group_maker = groups_module.ControlsGroups()

        # GRP raiz de cada control, para poder organizarlos al final.
        self.control_groups = []
        self.module_group = None

    # ------------------------------------------------------------------
    # GUIES
    # ------------------------------------------------------------------

    def _required_guides(self):
        """Guies que fan falta segons les features actives."""
        guides = [self.nose_root_guide, self.nose_tip_guide]

        if self.has("nostrils"):
            guides += [self.base_nostril_guide, self.nostril_guide]

        return guides

    def _missing_guides(self):
        return [g for g in self._required_guides() if not cmds.objExists(g)]

    # ------------------------------------------------------------------
    # JOINTS
    # ------------------------------------------------------------------

    def _create_joint_from_guide(self, guide_name, joint_name, mirror_x=False):
        """
        Crea un joint a la posicio d'una guia. Si mirror_x=True, inverteix
        la component X de la posicio -- aixi es treu el costat R sense que
        calgui cap guia R_ real a l'escena.
        """
        if not cmds.objExists(guide_name):
            cmds.warning(f"La guia {guide_name} no existeix.")
            return None

        pos = cmds.xform(guide_name, q=True, ws=True, t=True)
        if mirror_x:
            pos = [-pos[0], pos[1], pos[2]]

        cmds.select(clear=True)
        jnt = cmds.joint(name=joint_name)
        cmds.xform(jnt, ws=True, t=pos)

        return jnt

    def create_nose_joints(self):
        """Crea els joints principals del nas a partir de la posicio de les guies."""
        cmds.select(clear=True)

        self.nose_root_jnt = self._create_joint_from_guide(
            self.nose_root_guide, self.nose_root_jnt
        )
        self.nose_tip_jnt = self._create_joint_from_guide(
            self.nose_tip_guide, self.nose_tip_jnt
        )

        self.joints = [self.nose_root_jnt, self.nose_tip_jnt]

        # Les aletes son opcionals (feature "nostrils"): sense elles nomes hi
        # ha nose_root i nose_tip.
        if self.has("nostrils"):
            self.base_nostril_jnt = self._create_joint_from_guide(
                self.base_nostril_guide, self.base_nostril_jnt
            )

            # L es la posicio real de la guia; R surt de mirallar-ne la X.
            self.nostril_jnt["L"] = self._create_joint_from_guide(
                self.nostril_guide, self.nostril_jnt["L"], mirror_x=False
            )
            self.nostril_jnt["R"] = self._create_joint_from_guide(
                self.nostril_guide, self.nostril_jnt["R"], mirror_x=True
            )

            self.joints += [
                self.base_nostril_jnt,
                self.nostril_jnt["L"],
                self.nostril_jnt["R"],
            ]

        cmds.select(clear=True)
        return self.joints

    def duplicate_nostril_joints(self):
        """
        Duplica els dos joints de nostril (L i R) mantenint exactament la
        mateixa posicio. Nomes si "nostrils" i "nostril_dup" estan actives.
        parentOnly=True evita duplicar fills que pengin del joint original.
        """
        if not (self.has("nostrils") and self.has("nostril_dup")):
            return {}

        for side in ("L", "R"):
            dup = cmds.duplicate(
                self.nostril_jnt[side],
                name=self.nostril_jnt_dup[side],
                parentOnly=True,
            )[0]

            # Si el duplicat queda penjat com a fill de l'original, el
            # traiem a world.
            parent = cmds.listRelatives(dup, parent=True)
            if parent:
                cmds.parent(dup, world=True)

            self.nostril_jnt_dup[side] = dup
            self.joints.append(dup)

        return self.nostril_jnt_dup

    # ------------------------------------------------------------------
    # CONTROLADORS
    # ------------------------------------------------------------------

    def _make_control(self, name, target):
        """
        Crea un control i li monta la jerarquia GRP > SPC > OFF > SDK > ANIM.

        L'objectiu es el JOINT, no la guia: el nostril R no te guia pero si
        joint, i aixi els dos costats fan servir el mateix cami.

        match_rotation=True: el GRP agafa tambe l'orientacio del joint. Ara
        mateix els joints es creen sense rotacio, o sea que surt identitat,
        pero si algun dia s'orienten, els controls els seguiran sols.
        """
        if not target or not cmds.objExists(target):
            cmds.warning(f"[Nose] No existeix '{target}'. No creo '{name}'.")
            return None, None

        control = controlsLibrary.create_control_from_lib(
            lib_name="circle", final_name=name
        )

        group = self.group_maker.create_rig_hierarchy(
            control, target, match_rotation=True, world_space=True
        )

        self.controls.append(control)
        self.control_groups.append(group)

        return control, group

    def create_controllers(self):
        """
        Crea els controladors: nose_root i nose_tip sempre (son features
        "always"), i els dos nostrils + base_nostril nomes si "nostrils"
        esta activa.

        Ja no es posicionen amb un cmds.xform solt: cada un porta la seva
        jerarquia de grups, com la resta del rig. Aixi el control queda amb
        els canals a zero i hi ha SPC, OFF i SDK lliures per si despres cal
        penjar-hi space switches, correctius o driven keys.
        """
        self.nose_root_ctrl, _ = self._make_control(
            self.nose_root_ctrl, self.nose_root_jnt
        )
        self.nose_tip_ctrl, _ = self._make_control(
            self.nose_tip_ctrl, self.nose_tip_jnt
        )

        if not self.has("nostrils"):
            return self.controls

        for side in ("L", "R"):
            self.nostril_ctrl[side], _ = self._make_control(
                self.nostril_ctrl[side], self.nostril_jnt[side]
            )

        self.base_nostril_ctrl, _ = self._make_control(
            self.base_nostril_ctrl, self.base_nostril_jnt
        )

        return self.controls

    # ------------------------------------------------------------------
    # CONSTRAINTS
    # ------------------------------------------------------------------

    def constraint_joints_to_controllers(self):
        """
        Parent constraint de nose_root i nose_tip al seu control (sempre),
        dels joints de cada nostril (original + duplicat, si n'hi ha) cap
        al seu propi controlador, i del joint de base_nostril cap al seu
        controlador de centre (nomes si "nostrils" esta activa).
        """
        cmds.parentConstraint(
            self.nose_root_ctrl, self.nose_root_jnt, maintainOffset=True
        )
        cmds.parentConstraint(
            self.nose_tip_ctrl, self.nose_tip_jnt, maintainOffset=True
        )

        if not self.has("nostrils"):
            return

        for side in ("L", "R"):
            cmds.parentConstraint(
                self.nostril_ctrl[side], self.nostril_jnt[side], maintainOffset=True
            )

            if self.has("nostril_dup"):
                cmds.parentConstraint(
                    self.nostril_ctrl[side], self.nostril_jnt_dup[side],
                    maintainOffset=True,
                )

        cmds.parentConstraint(
            self.base_nostril_ctrl, self.base_nostril_jnt, maintainOffset=True
        )

    # ------------------------------------------------------------------
    # BUILD COMPLET
    # ------------------------------------------------------------------

    def build(self):
        """
        Executa tot el modul en ordre. Una sola crida construeix L i R.

        Torna None (i avisa) si falta alguna guia -- aixi build_module la
        pot saltar en lloc de petar, igual que fa amb la boca, el jaw, les
        celles i els ulls.
        """
        missing = self._missing_guides()
        if missing:
            cmds.warning(
                "[Nose] Falten guies ({}). Es salta el nas.".format(
                    ", ".join(missing))
            )
            return None

        self.create_nose_joints()
        self.duplicate_nostril_joints()
        self.create_controllers()
        self.constraint_joints_to_controllers()
        self.organize()

        return self.joints, self.controls

    def organize(self):
        """
        Recull els GRP dels controls sota un grup del modul, per no deixar-los
        solts a l'arrel de l'escena.
        """
        group_name = f"{self.center_prefix}nose_GRP"

        existing = [group for group in self.control_groups
                    if group and cmds.objExists(group)]
        if not existing:
            return None

        if cmds.objExists(group_name):
            cmds.delete(group_name)

        self.module_group = cmds.group(existing, n=group_name)

        return self.module_group