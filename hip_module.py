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
           ├ COGPivot_CTRL      el translate va al rotatePivot i scalePivot del body
           ├ bodyOut_TRN        -> parentConstraint -> body_JNT
           └ localHip_CTL

    Moure el COGPivot_CTRL no mou res: nomes canvia el punt sobre el qual gira
    i escala el body.

    Dues coses que cal vigilar amb aquest sistema i que el modul ja resol:
      - Si el body esta rotat o escalat, moure el pivot SI desplacaria el
        control. Es compensa calculant rotatePivotTranslate i scalePivotTranslate
        (compensate_pivot=True).
      - Un parentConstraint segueix el rotatePivot del target, aixi que el
        body_JNT es constreny a bodyOut_TRN (fill del body i en identitat).
    """

    def __init__(self,root_guide ="root", 
                rig_name="Character",
                root_instance=None,
                compensate_pivot=True
                ):
                    
        self.root_guide = root_guide
        self.rig_name  = rig_name
        
        #self.ctrl_maker = controls_module.Controls(scale=5, color=17) # 17 es amarillo
        self.ctrl_style = "hipControl"
        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance
        self.compensate_pivot = compensate_pivot
        self.body_ctl = None
        self.body_joint = None
        self.pivot_ctl = None

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

    def build_pivot_compensation(self, body_ctl, pivot_ctl):
        """
        Compensa el desplacament que provoca moure el pivot quan el control
        esta rotat o escalat:

            rotatePivotTranslate = RP - RP * R
            scalePivotTranslate  = SP - SP * S

        Sense aixo, moure el pivot amb el body rotat desplaca tot el rig una
        mica. Es el que fa Maya per dins quan mous el pivot a ma al viewport.
        """
        rig = self.rig_name

        # --- Rotacio ---
        rot_cmx = cmds.createNode("composeMatrix", n=f"{rig}_cogPivotRot_CMX")
        cmds.connectAttr(f"{body_ctl}.rotate", f"{rot_cmx}.inputRotate")

        rot_vpr = cmds.createNode("vectorProduct", n=f"{rig}_cogPivotRot_VPR")
        cmds.setAttr(f"{rot_vpr}.operation", 4)        # point matrix product
        cmds.connectAttr(f"{pivot_ctl}.translate", f"{rot_vpr}.input1")
        cmds.connectAttr(f"{rot_cmx}.outputMatrix", f"{rot_vpr}.matrix")

        rot_pma = cmds.createNode("plusMinusAverage", n=f"{rig}_cogPivotRot_PMA")
        cmds.setAttr(f"{rot_pma}.operation", 2)        # subtract
        cmds.connectAttr(f"{pivot_ctl}.translate", f"{rot_pma}.input3D[0]")
        cmds.connectAttr(f"{rot_vpr}.output", f"{rot_pma}.input3D[1]")
        cmds.connectAttr(f"{rot_pma}.output3D", f"{body_ctl}.rotatePivotTranslate")

        # --- Escala ---
        scl_mdv = cmds.createNode("multiplyDivide", n=f"{rig}_cogPivotScl_MDV")
        cmds.connectAttr(f"{pivot_ctl}.translate", f"{scl_mdv}.input1")
        cmds.connectAttr(f"{body_ctl}.scale", f"{scl_mdv}.input2")

        scl_pma = cmds.createNode("plusMinusAverage", n=f"{rig}_cogPivotScl_PMA")
        cmds.setAttr(f"{scl_pma}.operation", 2)
        cmds.connectAttr(f"{pivot_ctl}.translate", f"{scl_pma}.input3D[0]")
        cmds.connectAttr(f"{scl_mdv}.output", f"{scl_pma}.input3D[1]")
        cmds.connectAttr(f"{scl_pma}.output3D", f"{body_ctl}.scalePivotTranslate")

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

        # --- Control del pivot: penja del body ---
        pivot_ctl = controlsLibrary.create_control_from_lib(
            lib_name="bodyControl",
            final_name=f"{rig}_COGPivot_CTRL")
        pivot_off = self.group_maker.create_rig_hierarchy(pivot_ctl, self.root_guide)
        self.rotate_shape(pivot_ctl, 90, 0, 0)
        self.scale_shape(pivot_ctl, 0.5)
        cmds.parent(pivot_off, body_ctl)

        # Nomes es mou: rotar-lo o escalar-lo no te sentit
        for attr in ("rx", "ry", "rz", "sx", "sy", "sz"):
            cmds.setAttr(f"{pivot_ctl}.{attr}", lock=True, keyable=False, channelBox=False)

        # --- El translate del pivot mana els pivots del body ---
        cmds.connectAttr(f"{pivot_ctl}.translate", f"{body_ctl}.rotatePivot")
        cmds.connectAttr(f"{pivot_ctl}.translate", f"{body_ctl}.scalePivot")
        if self.compensate_pivot:
            self.build_pivot_compensation(body_ctl, pivot_ctl)

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

        self.pivot_ctl = pivot_ctl
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