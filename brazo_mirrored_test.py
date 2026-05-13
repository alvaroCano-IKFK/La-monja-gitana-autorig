    def build_mirror(self):
        """
        Construye el brazo del lado R reutilizando LimbModule.

        Estrategia: los controles R viven bajo localCtl en world space normal,
        sin ningun scaleX=-1 encima. Eso garantiza que mover Y+ en el control R
        mueve el joint R en Y+ (mismo comportamiento que el lado L).
        Las posiciones correctas (espejadas en X) vienen de las guias R
        que ya creo mirrorJoint.
        """

        def to_r(name):
            return name.replace("L_", "R_", 1)

        r_clavicule_guide = to_r(self.clavicule_guide)
        r_shoulder_guide  = to_r(self.shoulder_guide)
        r_elbow_guide     = to_r(self.elbow_guide)
        r_wrist_guide     = to_r(self.wrist_guide)

        missing = [g for g in [r_clavicule_guide, r_shoulder_guide,
                                r_elbow_guide, r_wrist_guide]
                   if not cmds.objExists(g)]
        if missing:
            cmds.warning(
                f"build_mirror: faltan guias R: {missing}. "
                "Ejecuta mirror_module.Mirror().mirror() primero."
            )
            return None

        r_rig_name = self.rig_name.replace("_L", "_R", 1)

        r_arm = LimbModule(
            shoulder_guide  = r_shoulder_guide,
            elbow_guide     = r_elbow_guide,
            wrist_guide     = r_wrist_guide,
            clavicule_guide = r_clavicule_guide,
            rig_name        = r_rig_name,
            root_instance   = self.root_instance
        )
        r_arm.names = [n.replace("L_", "R_") for n in self.names]
        r_arm.build()

        # Todos los controles R bajo localCtl, en world space limpio.
        # Sin mirror_grp (scaleX=-1) encima: mover Y+ en R mueve el joint en Y+.
        # La posicion espejada ya viene de las guias R (mirrorJoint).
        local_ctl = self.root_instance.localCtl if self.root_instance else None

        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(r_arm.main_rig_grp, local_ctl)
            cmds.parent(r_arm.arm_grp,      local_ctl)
            print(f"build_mirror: {r_rig_name} emparentado a {local_ctl} (world space limpio)")
        else:
            cmds.warning("build_mirror: no se encontro localCtl.")

        return r_arm