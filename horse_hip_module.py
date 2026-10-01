import maya.cmds as cmds
import horse_spine
import controlsLibrary
import guides_module
import groups_module 


class HipModule(object):
    """
    Hip local + BODY (COG) amb pivot movible.

        local_CTL
         └ body_CTL             COG del rig
           ├ COG_CTRL           translationFromMatrix -> rotatePivot i scalePivot
           ├ bodyOut_TRN        -> parentConstraint -> body_JNT
           └ localHip_CTL

    El COG_CTRL es crea a la mateixa posicio que el body i tota la seva
    jerarquia de grups penja del body_CTL. La seva matriu passa per un
    translationFromMatrix i la translacio va als pivots del body: moure el
    COG_CTRL no mou res, nomes canvia el punt sobre el qual gira i escala.

    El body_JNT es constreny a bodyOut_TRN (fill del body i en identitat)
    perque un parentConstraint segueix el rotatePivot del target.
    """

    def __init__(self,root_guide ="root", 
                rig_name="Character",
                root_instance=None
                ):
                    
        self.root_guide = root_guide
        self.rig_name  = rig_name
        
        #self.ctrl_maker = controls_module.Controls(scale=5, color=17) # 17 es amarillo
        self.ctrl_style = "hipControl"
        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance
        self.body_ctl = None
        self.body_joint = None
        self.cog_ctl = None

    # ------------------------------------------------------------------ #
    # BODY (COG) AMB PIVOT MOVIBLE
    # ------------------------------------------------------------------ #
    def scale_shape(self, ctrl, factor):
        """Escala les CVs de la forma del control sense tocar el transform."""
        shapes = cmds.listRelatives(ctrl, s=True) or []
        pivot = cmds.xform(ctrl, q=True, ws=True, rp=True)
        for shape in shapes:
            num_cvs = cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")
            cvs = [f"{shape}.cv[{j}]" for j in range(num_cvs)]
            cmds.scale(factor, factor, factor, cvs, r=True, p=pivot, ws=True)

    def rotate_shape(self, ctrl, rx, ry, rz):
        """Gira les CVs de la forma del control sense tocar el transform."""
        shapes = cmds.listRelatives(ctrl, s=True) or []
        pivot = cmds.xform(ctrl, q=True, ws=True, rp=True)
        for shape in shapes:
            num_cvs = cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")
            cvs = [f"{shape}.cv[{j}]" for j in range(num_cvs)]
            cmds.rotate(rx, ry, rz, cvs, r=True, p=pivot, ws=True)

    def build_body(self):
        """Crea el COG amb pivot movible i el joint del body."""
        rig = self.rig_name
        body_name = f"{rig}_body_CTL"
        if cmds.objExists(body_name):
            cmds.warning(f"[HipModule] {body_name} ja existeix: no es torna a crear.")
            self.body_ctl = body_name
            return body_name

        pos_body = cmds.xform(self.root_guide, q=True, ws=True, t=True)

        # --- Body (COG) ---
        body_ctl = controlsLibrary.create_control_from_lib(
            lib_name="bodyControl",
            final_name=body_name)
        body_off = self.group_maker.create_rig_hierarchy(body_ctl, self.root_guide)
        self.rotate_shape(body_ctl, 90, 0, 0)

        # --- Control del COG: mateixa posicio que el body i penjat d ell ---
        cog_ctl = controlsLibrary.create_control_from_lib(
            lib_name="bodyControl",
            final_name=f"{rig}_COG_CTRL")
        cog_off = self.group_maker.create_rig_hierarchy(cog_ctl, self.root_guide)
        self.rotate_shape(cog_ctl, 90, 0, 0)
        self.scale_shape(cog_ctl, 0.5)
        cmds.parent(cog_off, body_ctl)

        # Nomes es mou: rotar-lo o escalar-lo no te sentit
        for attr in ("rx", "ry", "rz", "sx", "sy", "sz"):
            cmds.setAttr(f"{cog_ctl}.{attr}", lock=True, keyable=False, channelBox=False)

        # --- La matriu del COG mana els pivots del body ---
        if "translationFromMatrix" in (cmds.allNodeTypes() or []):
            tfm = cmds.createNode("translationFromMatrix", n=f"{rig}_cogPivot_TFM")
            cmds.connectAttr(f"{cog_ctl}.matrix", f"{tfm}.input")
            out_plug = f"{tfm}.output"
        else:
            # Maya sense els nodes de matematiques nous
            tfm = cmds.createNode("decomposeMatrix", n=f"{rig}_cogPivot_DCM")
            cmds.connectAttr(f"{cog_ctl}.matrix", f"{tfm}.inputMatrix")
            out_plug = f"{tfm}.outputTranslate"

        cmds.connectAttr(out_plug, f"{body_ctl}.rotatePivot")
        cmds.connectAttr(out_plug, f"{body_ctl}.scalePivot")

        # --- Sortida per al joint: filla del body i en identitat, aixi no li
        #     afecta el pivot (un parentConstraint si que seguiria el pivot) ---
        out = cmds.createNode("transform", n=f"{rig}_bodyOut_TRN", parent=body_ctl)

        cmds.select(clear=True)
        body_joint = cmds.joint(n=f"{rig}_body_JNT", p=pos_body)
        cmds.select(clear=True)

        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            body_joint = cmds.parent(body_joint, rig_grp)[0]
        cmds.parentConstraint(out, body_joint, mo=True, n=f"{rig}_body_PAC")

        # --- Organitzacio ---
        local_ctl = self.root_instance.localCtl if self.root_instance else None
        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(body_off, local_ctl)

        if self.root_instance:
            self.root_instance.body_ctl = body_ctl   # el publiquem per als altres moduls

        self.cog_ctl = cog_ctl
        self.body_ctl = body_ctl
        self.body_joint = body_joint
        print(f"[HipModule] Body amb pivot movible creat: {body_ctl}")
        return body_ctl

    def build(self):

        # El COG va primer: el hip local hi penja
        self.build_body()

        pos_hip = cmds.xform(self.root_guide,q=True, ws=True, t=True) 
        
        cmds.select(clear = True)
        
        hip_joint = cmds.joint(n=f"{self.rig_name}_hip_JNT", p=pos_hip)

        hip_end_pos =[
                    pos_hip[0],
                    pos_hip[1]-2.5,
                    pos_hip[2]
                    ]
                    
        hip_end_joint = cmds.joint(n=f"{self.rig_name}_hipEnd_JNT", p =hip_end_pos)
        
        
        
        name = f"{self.rig_name}_localHip_CTL"
        hipControl = controlsLibrary.create_control_from_lib(
            lib_name=self.ctrl_style, 
            final_name=name)
        
        # Cambio aquí
        hipControl_off = self.group_maker.create_rig_hierarchy(hipControl, self.root_guide)
        cmds.parentConstraint(hipControl, hip_joint)
        
        # Conectar el hip CTL como World Up End del IK de la espina
        ik_name = f"{self.rig_name}_spine_IK"
        if cmds.objExists(ik_name) and cmds.objExists(hipControl):
            cmds.connectAttr(f"{hipControl}.worldMatrix[0]", f"{ik_name}.dWorldUpMatrixEnd", force=True)
            print(f"Hip CTL conectado al twist de la espina.")
                
        # ORGANIZACIÓN FINAL
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )
        if rig_grp  and cmds.objExists(rig_grp ):
            cmds.parent(hip_joint , rig_grp )
            
        self.hip_control_name = hipControl      
        self.hip_group_name = hipControl_off
        
        # METER LOS CONTROLADORES DENTRO DEL LOCAL CONTROL            
        local_ctl = self.root_instance.localCtl if self.root_instance else None
        body_ctl = self.root_instance.body_ctl if self.root_instance else None

        if body_ctl and cmds.objExists(body_ctl):
            cmds.parent(hipControl_off, body_ctl)