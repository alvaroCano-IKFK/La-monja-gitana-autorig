import maya.cmds as cmds
import math
import controlsLibrary 
import guides_module
from groups_module import ControlsGroups
import rigRoot_module
import nodeCreator_module
import hip_module
from nodeCreator_module import NodeCreator
import curvature_module
import twist_module
import chest_module


class LegModule(object):
    """Módulo para construir las piernas, con setup IK/FK y switch."""

    def __init__(self,
                 clavicule_start_guide="L_clavicule_start",
                 clavicule_guide="clavicule", 
                 thigh_guide="hip", 
                 knee_guide="knee", 
                 ankle_guide="ankle",
                 ball_guide ="ball", 
                 tip_guide = "toe_tip",
                 heel_guide = "heel",  
                 rig_name="Character",
                 side = "L",
                 hip_instance= None,
                 root_instance= None,
                 clavicule_parent="Character_chestFix_CTL",
                 hoof=False,
                 bank_in_guide=None,
                 bank_out_guide=None,
                 scapula=False,
                 clavicle=True,
                 three_bone=False,
                 hock_guide=None,
                 scapula_pivot_ratio=1.0 / 3.0):
        
        self.clavicule_start_guide = clavicule_start_guide
        self.clavicule_guide = clavicule_guide             
        self.thigh_guide = thigh_guide
        self.knee_guide = knee_guide
        self.ankle_guide = ankle_guide
        self.ball_guide = ball_guide
        self.tip_guide = tip_guide
        self.heel_guide = heel_guide
        
        self.side = side
        self.prefix = f"{self.side}_{rig_name}"         
        
        #PATA DE 3 SEGMENTS (pota del darrere del quadrupede). Amb three_bone=True:
        #  thigh = maluc, knee = babilla, hock = garro, ankle = menudillo
        #  IK amb ikSpringSolver de maluc a menudillo
        #SENSE CLAVICULA (clavicle=False): no hi ha controls de clavicula;
        #  el legRoot_CTRL penja directament de clavicule_parent (la pelvis)
        self.clavicle = clavicle
        self.three_bone = three_bone
        self.hock_guide = hock_guide
        if self.three_bone and not hock_guide:
            cmds.error(f"[{self.prefix}] three_bone=True necessita hock_guide")
        if scapula and not clavicle:
            cmds.error(f"[{self.prefix}] scapula=True necessita clavicle=True")

        #Noms de la cadena principal (sense heel, que no es joint de la cadena)
        if self.three_bone:
            self.names = ["thigh", "knee", "hock", "ankle", "ball", "toe_tip"]
        else:
            self.names = ["thigh", "knee", "ankle", "ball", "toe_tip"]
        self.i_ankle = self.names.index("ankle")
        self.i_ball = self.names.index("ball")
        self.i_tip = self.names.index("toe_tip")
        self.rig_name = rig_name
        self.styles = {"mainIk": "squareControl",
                              "mainFk": "circleControl",
                              "footBall": "footBallControl",
                              "footTip": "footTipControl",
                              "footHeel": "footHeelControl",
                              "footBankIn": "footBankInControl",
                              "footBankOut": "footBankOutControl",
                              "footRoot": "rootControl",
                              "switch": "switchControl",
                              "poleVector": "legPoleVectorControl",
                              "clavicule":  "claviculeControl"}
        
        self.group_maker = ControlsGroups()
        self.leg_grp = None
        
        self.root_instance = root_instance 
        self.hip_instance = hip_instance

        #Control al que es constreny la clavicula: el chest per a les cames de
        #davant, el hip per a les pates del darrere del quadrupede
        self.clavicule_parent = clavicule_parent

        #CASC (quadrupede). Amb hoof=True:
        #  ankle = menudillo, ball = corona, toe_tip = lumbre, heel = talons
        #  els pivots de bank van a les guies bank_in/bank_out (sense offsets fixos)
        #  s afegeix hoofCurl i els atributs FetlockBend, HoofCurl, Bank i HoofTwist
        self.hoof = hoof
        self.bank_in_guide = bank_in_guide
        self.bank_out_guide = bank_out_guide
        if self.hoof and not (bank_in_guide and bank_out_guide):
            cmds.error(f"[{self.prefix}] hoof=True necessita bank_in_guide i bank_out_guide")

        #ESCAPULA (pota de davant del quadrupede). Amb scapula=True:
        #  clavicule_start = vora superior de l escapula, clavicule = punta de l espatlla
        #  l escapula gira sobre un pivot al terc superior i apunta al shoulder_CTRL
        #  AutoScapula fa que l espatlla segueixi el legIk_CTRL
        self.scapula = scapula
        self.scapula_pivot_ratio = scapula_pivot_ratio

        self.bind_chain = []
        self.ik_chain = []
        self.fk_chain = []
        self.leg_joints_grp = None

    def create_offset_group(self, ctrl, target_proc, orient=False, world_space=True):
        """Crea un grupo de offset para el control, alineado con el target_proc."""
        return self.group_maker.create_rig_hierarchy(
            ctrl, 
            target_proc, 
            match_rotation=orient, 
            world_space=world_space
    )
    
    def define_poleVector(self, start, mid, end, distance=15):
        """Calcula la posición del pole vector basándose en la posición de los joints."""
        # NO TOCADO: Tu método original exacto
        sh_p = cmds.xform(start, q=True, ws=True, t=True)
        el_p = cmds.xform(mid, q=True, ws=True, t=True)
        wr_p = cmds.xform(end, q=True, ws=True, t=True)

        sw = [wr_p[i] - sh_p[i] for i in range(3)]
        se = [el_p[i] - sh_p[i] for i in range(3)]

        dot = sum(se[i] * sw[i] for i in range(3))
        mag_sq = sum(sw[i] * sw[i] for i in range(3))
        
        if mag_sq < 0.0001: return el_p
        
        proj = [(dot / mag_sq) * sw[i] for i in range(3)]
        perp = [se[i] - proj[i] for i in range(3)]
        
        length = math.sqrt(sum(v * v for v in perp))
        if length < 0.0001:
            perp = [0, 0, 1] 
        else:
            perp = [v / length for v in perp]

        return [el_p[i] + perp[i] * distance for i in range(3)]
    

    def load_spring_plugin(self):
        """
        Assegura que el plugin ikSpringSolver esta carregat i que existeix el
        node solver a l escena.

        ikHandle(sol=...) no crea el solver: busca un node amb aquest nom.
        Els solvers de serie (ikRPsolver, ikSCsolver) ja hi son a cada escena,
        pero el spring s ha de crear a ma un cop carregat el plugin.
        """
        if not cmds.pluginInfo("ikSpringSolver", q=True, loaded=True):
            try:
                cmds.loadPlugin("ikSpringSolver", quiet=True)
            except RuntimeError:
                cmds.error("No s ha pogut carregar el plugin ikSpringSolver")

        if not cmds.ls(type="ikSpringSolver"):
            cmds.createNode("ikSpringSolver", n="ikSpringSolver")

        # Nom real del solver (per si Maya l ha renombrat)
        return cmds.ls(type="ikSpringSolver")[0]

    def build_spring_attrs(self, ik_ctrl, ik_h):
        """
        SpringBias al legIk_CTRL: reparteix la flexio entre babilla i garro.
        0 = doblega mes a dalt (babilla), 1 = doblega mes a baix (garro).
        Es connecta a la rampa springAngleBias del handle.
        """
        if not cmds.attributeQuery("springAngleBias", node=ik_h, exists=True):
            cmds.warning(f"[{self.prefix}] {ik_h} no te springAngleBias; SpringBias no connectat.")
            return

        cmds.addAttr(ik_ctrl, ln="springAttrSep", nn="SPRING", at="enum", en="------", k=False)
        cmds.setAttr(f"{ik_ctrl}.springAttrSep", cb=True)
        cmds.setAttr(f"{ik_ctrl}.springAttrSep", l=True)
        cmds.addAttr(ik_ctrl, ln="SpringBias", at="float", min=0, max=1, dv=0.5, k=True)

        bias_rev = cmds.createNode("reverse", n=f"{self.prefix}_springBias_REV")
        cmds.connectAttr(f"{ik_ctrl}.SpringBias", f"{bias_rev}.inputX")

        # La rampa ja ve amb dos punts (inici i final de la cadena) i les seves
        # posicions estan bloquejades: no es toquen, nomes es busca quin punt
        # es l inici i quin el final i se n connecta el valor.
        ramp = f"{ik_h}.springAngleBias"
        indices = cmds.getAttr(ramp, multiIndices=True) or []
        if len(indices) < 2:
            cmds.warning(f"[{self.prefix}] La rampa springAngleBias no te 2 punts; SpringBias no connectat.")
            return

        positions = {i: cmds.getAttr(f"{ramp}[{i}].springAngleBias_Position") for i in indices}
        start_idx = min(positions, key=positions.get)   # babilla (inici)
        end_idx = max(positions, key=positions.get)     # garro (final)

        try:
            cmds.connectAttr(f"{bias_rev}.outputX",
                             f"{ramp}[{start_idx}].springAngleBias_FloatValue", force=True)
            cmds.connectAttr(f"{ik_ctrl}.SpringBias",
                             f"{ramp}[{end_idx}].springAngleBias_FloatValue", force=True)
        except RuntimeError as err:
            cmds.warning(f"[{self.prefix}] No s ha pogut connectar SpringBias: {err}")

    def build_scapula_aim(self, scapula_ctrl, shoulder_ctrl, pos_top, pos_shoulder):
        """
        Escapula amb pivot real.

        scapula_CTRL
         |- scapulaUp_GRP     orientat al mon a la posa de repos (up de l aim)
         |- scapulaAim_GRP    al terc superior, aimConstraint -> shoulder_CTRL
             |- scapulaTop_DRV     vora superior  -> bind claviculeStart
             |- shoulderPoint_DRV  punta espatlla -> bind clavicule, FK, IK root

        L escapula no s estira: nomes gira. Si l espatlla va endavant,
        la vora superior va enrere tota sola.
        Tot es a posicions reals (els controls de clavicula no passen pel mirror).
        """
        p = self.prefix
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

        r = self.scapula_pivot_ratio
        pivot = [pos_top[i] + (pos_shoulder[i] - pos_top[i]) * r for i in range(3)]

        aim_dir = [pos_shoulder[i] - pivot[i] for i in range(3)]
        length = math.sqrt(sum(v * v for v in aim_dir))
        if length < 0.0001:
            cmds.error(f"[{p}] Les guies de l escapula estan al mateix punt")
        aim_dir = [v / length for v in aim_dir]

        def world_aligned(name, parent, pos):
            node = cmds.createNode("transform", n=name, parent=parent)
            cmds.xform(node, ws=True, m=identity)
            cmds.xform(node, ws=True, t=pos)
            return node

        up_grp = world_aligned(f"{p}_scapulaUp_GRP", scapula_ctrl, pivot)
        aim_grp = world_aligned(f"{p}_scapulaAim_GRP", scapula_ctrl, pivot)
        top_drv = world_aligned(f"{p}_scapulaTop_DRV", aim_grp, pos_top)
        shoulder_drv = world_aligned(f"{p}_shoulderPoint_DRV", aim_grp, pos_shoulder)

        # Les guies de l escapula estan al pla sagital: l eix X del mon
        # (lateral) es perpendicular a la direccio i fa d up sense flips
        cmds.aimConstraint(
            shoulder_ctrl, aim_grp, mo=True,
            aimVector=aim_dir, upVector=(1, 0, 0),
            worldUpType="objectrotation", worldUpVector=(1, 0, 0),
            worldUpObject=up_grp,
            n=f"{p}_scapulaAim_AIM"
        )
        return {"aim": aim_grp, "top": top_drv, "shoulder": shoulder_drv}

    def build_auto_scapula(self, scapula_ctrl, shoulder_gen, ik_ctrl, ik_mode_plug,
                           pos_top, pos_shoulder):
        """
        AutoScapula: l SDK del shoulder_CTRL rep una part del desplacament del
        legIk_CTRL, en espai de l escapula.

          offset = clamp( delta_legIk * Factor * AutoScapula * modeIK , +-Limit )

        L animador pot seguir corregint movent el shoulder_CTRL.
        """
        p = self.prefix
        length = math.sqrt(sum((pos_shoulder[i] - pos_top[i]) ** 2 for i in range(3)))

        cmds.addAttr(scapula_ctrl, ln="scapulaAttrSep", nn="SCAPULA", at="enum", en="------", k=False)
        cmds.setAttr(f"{scapula_ctrl}.scapulaAttrSep", cb=True)
        cmds.setAttr(f"{scapula_ctrl}.scapulaAttrSep", l=True)
        cmds.addAttr(scapula_ctrl, ln="AutoScapula", at="float", min=0, max=1, dv=1, k=True)
        cmds.addAttr(scapula_ctrl, ln="AutoScapulaFactor", at="float", min=0, dv=0.25, k=True)
        cmds.addAttr(scapula_ctrl, ln="AutoScapulaLimit", at="float", min=0, dv=round(length * 0.4, 3), k=True)

        sdk = shoulder_gen.replace("_GRP", "_SDK")
        if not cmds.objExists(sdk):
            cmds.warning(f"[{p}] No existeix {sdk}, AutoScapula no connectat.")
            return

        # Delta del legIk en els eixos de l SDK de l espatlla
        rest = cmds.createNode("transform", n=f"{p}_autoScapulaRest_GRP", parent=scapula_ctrl)
        cmds.matchTransform(rest, sdk, pos=False, rot=True)
        cmds.xform(rest, ws=True, t=cmds.xform(ik_ctrl, q=True, ws=True, rp=True))
        follow = cmds.createNode("transform", n=f"{p}_autoScapula_DRV", parent=rest)
        cmds.pointConstraint(ik_ctrl, follow, mo=True, n=f"{p}_autoScapula_PNC")

        # Pes = AutoScapula * modeIK
        weight = cmds.createNode("multDoubleLinear", n=f"{p}_autoScapulaWeight_MDL")
        cmds.connectAttr(f"{scapula_ctrl}.AutoScapula", f"{weight}.input1")
        cmds.connectAttr(ik_mode_plug, f"{weight}.input2")

        factor = cmds.createNode("multDoubleLinear", n=f"{p}_autoScapulaFactor_MDL")
        cmds.connectAttr(f"{weight}.output", f"{factor}.input1")
        cmds.connectAttr(f"{scapula_ctrl}.AutoScapulaFactor", f"{factor}.input2")

        scale = cmds.createNode("multiplyDivide", n=f"{p}_autoScapula_MDV")
        cmds.connectAttr(f"{follow}.translate", f"{scale}.input1")
        for ax in "XYZ":
            cmds.connectAttr(f"{factor}.output", f"{scale}.input2{ax}")

        # Limit simetric
        neg = cmds.createNode("multDoubleLinear", n=f"{p}_autoScapulaLimitNeg_MDL")
        cmds.setAttr(f"{neg}.input2", -1)
        cmds.connectAttr(f"{scapula_ctrl}.AutoScapulaLimit", f"{neg}.input1")

        clp = cmds.createNode("clamp", n=f"{p}_autoScapula_CLP")
        cmds.connectAttr(f"{scale}.output", f"{clp}.input")
        for ch in "RGB":
            cmds.connectAttr(f"{neg}.output", f"{clp}.min{ch}")
            cmds.connectAttr(f"{scapula_ctrl}.AutoScapulaLimit", f"{clp}.max{ch}")

        cmds.connectAttr(f"{clp}.output", f"{sdk}.translate", force=True)

    def build_hoof_attrs(self, ik_ctrl, roll_ball_plug, ball_sdk, tip_sdk,
                         bank_in_sdk, bank_out_sdk, curl_sdk):
        """
        Atributs del casc al legIk_CTRL.

        FetlockBend : negatiu enfonsa el menudillo, positiu el flexiona
                      (se suma al roll automatic del ball)
        HoofCurl    : positiu plega el casc cap enrere (pota enlaire)
        Bank        : positiu recolza a la vora interna, negatiu a l externa
        HoofTwist   : gira el casc sobre la lumbre
        """
        # El roll del caball trenca abans que el d un peu huma
        cmds.setAttr(f"{ik_ctrl}.RollLiftAngle", 30)
        cmds.setAttr(f"{ik_ctrl}.RollStraightAngle", 60)

        cmds.addAttr(ik_ctrl, ln="hoofAttrSep", nn="HOOF", at="enum", en="------", k=False)
        cmds.setAttr(f"{ik_ctrl}.hoofAttrSep", cb=True)
        cmds.setAttr(f"{ik_ctrl}.hoofAttrSep", l=True)
        for attr in ("FetlockBend", "HoofCurl", "Bank", "HoofTwist"):
            cmds.addAttr(ik_ctrl, ln=attr, at="float", dv=0, k=True)

        # FetlockBend + roll automatic -> ball SDK
        fet_pma = cmds.createNode("plusMinusAverage", n=f"{self.prefix}_fetlockBend_PMA")
        cmds.connectAttr(roll_ball_plug, f"{fet_pma}.input1D[0]")
        cmds.connectAttr(f"{ik_ctrl}.FetlockBend", f"{fet_pma}.input1D[1]")
        cmds.connectAttr(f"{fet_pma}.output1D", f"{ball_sdk}.rotateX", force=True)

        # HoofCurl -> pivot de la corona
        cmds.connectAttr(f"{ik_ctrl}.HoofCurl", f"{curl_sdk}.rotateX")

        # Bank: positiu -> bankIn, negatiu -> bankOut
        bank_clp = cmds.createNode("clamp", n=f"{self.prefix}_bank_CLP")
        cmds.setAttr(f"{bank_clp}.maxR", 180)
        cmds.setAttr(f"{bank_clp}.minG", -180)
        cmds.connectAttr(f"{ik_ctrl}.Bank", f"{bank_clp}.inputR")
        cmds.connectAttr(f"{ik_ctrl}.Bank", f"{bank_clp}.inputG")
        cmds.connectAttr(f"{bank_clp}.outputR", f"{bank_in_sdk}.rotateZ")
        cmds.connectAttr(f"{bank_clp}.outputG", f"{bank_out_sdk}.rotateZ")

        # HoofTwist -> pivot de la lumbre
        cmds.connectAttr(f"{ik_ctrl}.HoofTwist", f"{tip_sdk}.rotateY")

    def build(self):
        # 1. POSICIONES REALES (Para que los joints bind/ik/fk nazcan en el esqueleto real R)
        pos_cl_start = cmds.xform(self.clavicule_start_guide, q=True, ws=True, t=True) if self.clavicle else None
        pos_cl = cmds.xform(self.clavicule_guide, q=True, ws=True, t=True) if self.clavicle else None
        pos_th = cmds.xform(self.thigh_guide, q=True, ws=True, t=True)
        pos_kn = cmds.xform(self.knee_guide, q=True, ws=True, t=True)
        pos_an = cmds.xform(self.ankle_guide, q=True, ws=True, t=True)
        pos_ball = cmds.xform(self.ball_guide, q=True, ws=True, t=True)
        pos_tip = cmds.xform(self.tip_guide, q=True, ws=True, t=True)
        pos_heel = cmds.xform(self.heel_guide, q=True, ws=True, t=True)

        # 1b. OBJETIVOS PARA ALINEAR CONTROLES (Si es R, usamos L para que el grupo espejo haga el cálculo)
        if self.side == "R":
            clavicule_start_ctrl_target = self.clavicule_start_guide
            clavicule_ctrl_target = self.clavicule_guide
            th_ctrl_target = self.thigh_guide.replace("R_", "L_")
            kn_ctrl_target = self.knee_guide.replace("R_", "L_")
            hock_ctrl_target = self.hock_guide.replace("R_", "L_") if self.three_bone else None
            an_ctrl_target = self.ankle_guide.replace("R_", "L_")
            ball_ctrl_target = self.ball_guide.replace("R_", "L_")
            tip_ctrl_target = self.tip_guide.replace("R_", "L_")
            heel_ctrl_target = self.heel_guide.replace("R_", "L_")
            switch_ctrl_target = self.thigh_guide.replace("R_", "L_")
            bank_in_ctrl_target = self.bank_in_guide.replace("R_", "L_") if self.hoof else None
            bank_out_ctrl_target = self.bank_out_guide.replace("R_", "L_") if self.hoof else None
            
        else:
            clavicule_start_ctrl_target = self.clavicule_start_guide
            clavicule_ctrl_target = self.clavicule_guide
            th_ctrl_target = self.thigh_guide
            kn_ctrl_target = self.knee_guide
            hock_ctrl_target = self.hock_guide
            an_ctrl_target = self.ankle_guide
            ball_ctrl_target = self.ball_guide
            tip_ctrl_target = self.tip_guide
            heel_ctrl_target = self.heel_guide
            switch_ctrl_target = self.thigh_guide
            bank_in_ctrl_target = self.bank_in_guide
            bank_out_ctrl_target = self.bank_out_guide

        # 2. BIND CHAIN (Usa posiciones reales)
        b_cl_start = None
        c_cl = None
        if self.clavicle:
            cmds.select(clear=True)
            b_cl_start = cmds.joint(n=f"{self.prefix}_claviculeStart_bind_JNT", p=pos_cl_start)
            cmds.matchTransform(b_cl_start, self.clavicule_start_guide, rot=True, pos=True)

            cmds.select(clear=True)
            c_cl = cmds.joint(n=f"{self.prefix}_clavicule_bind_JNT", p=pos_cl)
            cmds.matchTransform(c_cl, self.clavicule_guide, rot=True, pos=True)

        # Cadena principal: (thigh, knee, [hock], ankle, ball, toe_tip)
        chain_guides = {
            "thigh": self.thigh_guide,
            "knee": self.knee_guide,
            "hock": self.hock_guide,
            "ankle": self.ankle_guide,
            "ball": self.ball_guide,
            "toe_tip": self.tip_guide,
        }
        self.bind_chain = []
        for name in self.names:
            guide = chain_guides[name]
            cmds.select(clear=True)
            jnt = cmds.joint(n=f"{self.prefix}_{name}_bind_JNT",
                             p=cmds.xform(guide, q=True, ws=True, t=True))
            # l ankle copia tambe la posicio, com abans
            cmds.matchTransform(jnt, guide, rot=True, pos=(name == "ankle"))
            if self.bind_chain:
                cmds.parent(jnt, self.bind_chain[-1])
            self.bind_chain.append(jnt)
        cmds.select(clear=True)

        b_th = self.bind_chain[0]
        if self.clavicle:
            cmds.parent(b_th, c_cl)
            cmds.parent(c_cl, b_cl_start)

        cmds.makeIdentity(b_th, apply=True, t=0, r=1, s=0, n=0, pn=1)

        # Arrel de l esquelet de la cama (el que va al leg_GRP)
        bind_root = b_cl_start if self.clavicle else b_th

        # Duplicate chains
        def duplicate_chain(suffix):
            new_jnts = cmds.duplicate(self.bind_chain[0], rc=True)
            root = cmds.rename(new_jnts[0], f"{self.prefix}_{self.names[0]}_{suffix}_JNT")
            children = cmds.listRelatives(root, ad=True, type="joint")
            children.reverse()
            chain = [root]
            for child, name in zip(children, self.names[1:]):
                chain.append(cmds.rename(child, f"{self.prefix}_{name}_{suffix}_JNT"))
            return chain
            
        self.fk_chain = duplicate_chain("fk")
        self.ik_chain = duplicate_chain("ik")
        
        cmds.setAttr(f"{self.ik_chain[0]}.visibility",0)
        cmds.setAttr(f"{self.fk_chain[0]}.visibility",0)
        
        # 3. GRUPOS DE RIG
        self.main_rig_grp = cmds.group(em=True, n=f"{self.prefix}_legControls_GRP")
        self.main_grp = self.main_rig_grp
        self.ik_grp = cmds.group(em=True, n=f"{self.prefix}_ik_GRP", p=self.main_rig_grp)
        self.fk_grp = cmds.group(em=True, n=f"{self.prefix}_fk_GRP", p=self.main_rig_grp)
        self.controls_grp = cmds.group(em=True, n=f"{self.prefix}_CONTROLS_GRP", p=self.main_rig_grp)
        self.leg_grp = cmds.group(em=True, n=f"{self.prefix}_leg_GRP")
        
        # 4. IK SETUP
        pref_rot = 0.1 if self.side == "L" else -0.1
        cmds.setAttr(f"{self.ik_chain[1]}.rotateX", pref_rot) 
        cmds.joint(self.ik_chain[0], edit=True, ch=True, spa=True) 
        cmds.setAttr(f"{self.ik_chain[1]}.rotateX", 0) 

        # ---- 4. IK HANDLES ----
        if self.three_bone:
            # Maluc -> babilla -> garro -> menudillo amb spring solver
            spring_solver = self.load_spring_plugin()
            ik_h, _ = cmds.ikHandle(sj=self.ik_chain[0], ee=self.ik_chain[self.i_ankle],
                                    sol=spring_solver, n=f"{self.prefix}_IKH")
        else:
            ik_h, _ = cmds.ikHandle(sj=self.ik_chain[0], ee=self.ik_chain[self.i_ankle],
                                    sol="ikRPsolver", n=f"{self.prefix}_IKH")
        ik_footBall, _ = cmds.ikHandle(sj=self.ik_chain[self.i_ankle], ee=self.ik_chain[self.i_ball],
                                        sol="ikSCsolver", n=f"{self.prefix}_footBall_HDL")
        ik_footTip, _  = cmds.ikHandle(sj=self.ik_chain[self.i_ball], ee=self.ik_chain[self.i_tip],
                                        sol="ikSCsolver", n=f"{self.prefix}_footTip_HDL")
        cmds.select(clear=True)
        
        # IK Controls (Alineados con los targets corregidos)
        
        clav_ctls = []
        clavicule_start_ctrl = clavicule_start_gen = None
        clavicule_ctrl = clavicule_gen = None
        if self.clavicle:
        
            clavicule_start_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["clavicule"], 
                final_name=f"{self.prefix}_scapula_CTRL" if self.scapula else f"{self.prefix}_claviculeStart_CTRL"
            )
        
            clavicule_start_gen = self.create_offset_group(clavicule_start_ctrl, clavicule_start_ctrl_target, orient=True)
        
            clavicule_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["clavicule"], 
                final_name=f"{self.prefix}_shoulder_CTRL" if self.scapula else f"{self.prefix}_clavicule_CTRL"
            )
            clavicule_gen = self.create_offset_group(clavicule_ctrl, clavicule_ctrl_target, orient=True)
        
            clav_ctls.append(clavicule_start_ctrl)
            clav_ctls.append(clavicule_ctrl)
        
        ik_root_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footRoot"], 
            final_name=f"{self.prefix}_legRoot_CTRL"
        )
        ik_root_gen = self.create_offset_group(ik_root_ctrl, th_ctrl_target, orient=True)
                
        ik_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainIk"], 
            final_name=f"{self.prefix}_legIk_CTRL"
        )
        ik_gen = self.create_offset_group(ik_ctrl, an_ctrl_target, world_space=True)
        
        foot_heel_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footHeel"], 
            final_name=f"{self.prefix}_footHeel_CTRL"
        )
        foot_heel_gen = self.create_offset_group(foot_heel_ctrl, heel_ctrl_target, world_space=True)        
        if not self.hoof:
            cmds.xform(foot_heel_gen, r=True, t=(0, -0.3, -2))
        
        foot_ball_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBall"], 
            final_name=f"{self.prefix}_footBall_CTRL"
        )
        foot_ball_gen = self.create_offset_group(foot_ball_ctrl, ball_ctrl_target, world_space=True)
        
        foot_tip_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footTip"], 
            final_name=f"{self.prefix}_footTip_CTRL"
        )
        foot_tip_gen = self.create_offset_group(foot_tip_ctrl, tip_ctrl_target, world_space=True)
        if not self.hoof:
            cmds.xform(foot_tip_gen, r=True, t=(0, -0.3, 2))
        
        foot_bankIn_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBankIn"], 
            final_name=f"{self.prefix}_footBankIn_CTRL"
        )
        if self.hoof:
            foot_bankIn_gen = self.create_offset_group(foot_bankIn_ctrl, bank_in_ctrl_target, world_space=True)
        else:
            foot_bankIn_gen = self.create_offset_group(foot_bankIn_ctrl, ball_ctrl_target, world_space=True)
            cmds.xform(foot_bankIn_gen, r=True, t=(-3, -0.3, 0))
                
        foot_bankOut_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBankOut"], 
            final_name=f"{self.prefix}_footBankOut_CTRL"
        )
        if self.hoof:
            foot_bankOut_gen = self.create_offset_group(foot_bankOut_ctrl, bank_out_ctrl_target, world_space=True)
        else:
            foot_bankOut_gen = self.create_offset_group(foot_bankOut_ctrl, ball_ctrl_target, world_space=True)
            cmds.xform(foot_bankOut_gen, r=True, t=(3, -0.3, 0))

        # Hoof curl: pivot a la corona, germa del footBall. Plega el casc cap
        # enrere sense moure el menudillo (pota enlaire).
        hoof_curl_ctrl = None
        hoof_curl_gen = None
        if self.hoof:
            hoof_curl_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["footBall"],
                final_name=f"{self.prefix}_hoofCurl_CTRL"
            )
            hoof_curl_gen = self.create_offset_group(hoof_curl_ctrl, ball_ctrl_target, world_space=True)
        
        # Switch Control (Alineado con el target relativo)
        switch_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["switch"],
            final_name=f"{self.prefix}_switch_CTRL")
        switch_gen = self.group_maker.create_rig_hierarchy(switch_ctrl, switch_ctrl_target)
        switch_offset_x = 14 if self.side == "L" else -14
        cmds.xform(switch_gen, r=True, t=(switch_offset_x, 0, 0))     
        #cmds.xform(switch_gen, r = True,t=(14,0,0) )
        
           
        pv_pos = self.define_poleVector(self.ik_chain[0], self.ik_chain[1], self.ik_chain[self.i_ankle], distance=15)
        pv_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["poleVector"],
            final_name=f"{self.prefix}_poleVector_CTRL")
        
        pv_gen = self.group_maker.create_rig_hierarchy(pv_ctrl, self.ik_chain[1], world_space=False)
        cmds.xform(pv_gen, ws=True, t=pv_pos)
        
        # Si es el lado R, invertimos su TX local en el grupo para compensar el espejo negativo
        if self.side == "R":
            cur_tx = cmds.getAttr(f"{pv_gen}.translateX")
            cmds.setAttr(f"{pv_gen}.translateX", -cur_tx)

        # Sense clavicula el legRoot es l unic control de dalt: va al CONTROLS_GRP
        # perque es vegi tambe en mode FK (en fa de raiz)
        cmds.parent(ik_root_gen, self.ik_grp if self.clavicle else self.controls_grp)
        cmds.parent(
            ik_gen,
            foot_heel_gen, foot_ball_gen, foot_tip_gen,
            foot_bankIn_gen, foot_bankOut_gen, pv_gen,
            self.ik_grp
        )
        if hoof_curl_gen:
            # abans del mirror, igual que la resta de pivots
            cmds.parent(hoof_curl_gen, self.ik_grp)
        # FK Setup (Alineado con targets corregidos y solucionado el desfase del toe_tip)
        fk_ctrls = []
        fk_gens = []
        if self.three_bone:
            fk_targets = [th_ctrl_target, kn_ctrl_target, hock_ctrl_target, an_ctrl_target, ball_ctrl_target]
        else:
            fk_targets = [th_ctrl_target, kn_ctrl_target, an_ctrl_target, ball_ctrl_target]
        n_fk = len(fk_targets)   # tots menys el toe_tip
        for i in range(n_fk):
            ctrl_name = f"{self.prefix}_{self.names[i]}_fk_CTRL" # names[i] soluciona el descolocado del control final
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"], 
                final_name=ctrl_name
            )
            gen = self.group_maker.create_rig_hierarchy(ctrl, fk_targets[i])
            fk_ctrls.append(ctrl)
            fk_gens.append(gen)
            
        for i in range(n_fk):
            if i == 0:
                cmds.parent(fk_gens[i], self.fk_grp)
            else:
                cmds.parent(fk_gens[i], fk_ctrls[i - 1])
        if fk_ctrls[-1]:
            pivot = cmds.xform(fk_ctrls[-1], q=True, ws=True, rp = True)
            shapes = cmds.listRelatives(fk_ctrls[-1], s=True)
            for shape in shapes:
                num_cvs = cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")
                cvs = [f"{shape}.cv[{j}]" for j in range(num_cvs)]
                cmds.rotate(0, 90, 0, cvs, r=True, p=pivot, ws=True)    
                            
        # ---- ESTRUCTURA DEL MIRROR (LADO R) ----
        if self.side == "R":
            mirror_behavior_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP"
            if cmds.objExists(mirror_behavior_grp):
                cmds.parent(self.main_rig_grp, mirror_behavior_grp)
                cmds.setAttr(f"{self.main_rig_grp}.scaleX", 1)
                cmds.setAttr(f"{self.main_rig_grp}.scaleY", 1)
                cmds.setAttr(f"{self.main_rig_grp}.scaleZ", 1)
                cmds.setAttr(f"{self.main_rig_grp}.rotateX", 0)
                cmds.setAttr(f"{self.main_rig_grp}.rotateY", 0)
                cmds.setAttr(f"{self.main_rig_grp}.rotateZ", 0)


        #if self.side == "L":
            #for ctrl in clav_ctls:
                # Volvemos a pedir el pivote en World Space para tener la posición real absoluta
                #pivot = cmds.xform(ctrl, q=True, ws=True, rp=True)
                #shapes = cmds.listRelatives(ctrl, s=True)
                
                #if shapes:
                    #for shape in shapes:
                        #num_cvs = cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")
                        #cvs = [f"{shape}.cv[{j}]" for j in range(num_cvs)]
                        
                        # REGLA DE ORO: Usamos el pivote del mundo (ws=True) para la posición, 
                        # pero forzamos a que la orientación de la rotación use el Objeto (os=True)
                        #cmds.rotate(0, 110, 0, cvs, r=True, p=pivot, os=True)
        # ---- JERARQUIA DEL PIE ----
        
        if self.clavicle:
            cmds.parent(clavicule_gen, clavicule_start_ctrl)
        cmds.parent(foot_heel_gen,    ik_ctrl)
        cmds.parent(foot_bankIn_gen,  foot_heel_ctrl)
        cmds.parent(foot_bankOut_gen, foot_bankIn_ctrl)
        cmds.parent(foot_tip_gen,     foot_bankOut_ctrl)
        cmds.parent(foot_ball_gen,    foot_tip_ctrl)
        if hoof_curl_gen:
            cmds.parent(hoof_curl_gen, foot_tip_ctrl)

        # ---- ESCAPULA ----
        # Sense escapula la clavicula funciona com sempre (FK directe).
        # Amb escapula, bind, FK i IK root segueixen els drivers de l aim.
        scapula_top_driver = clavicule_start_ctrl
        # sense clavicula, l arrel del FK segueix el legRoot
        shoulder_driver = clavicule_ctrl if self.clavicle else ik_root_ctrl
        if self.scapula:
            scap = self.build_scapula_aim(clavicule_start_ctrl, clavicule_ctrl,
                                          pos_cl_start, pos_cl)
            scapula_top_driver = scap["top"]
            shoulder_driver = scap["shoulder"]

        # ---- FK CONSTRAINTS ----
        for i in range(n_fk):
            cmds.parentConstraint(fk_ctrls[i], self.fk_chain[i])
        # El OFF del thigh FK recibe el constraint de la clavicula.
        # GRP/SPC son para posicionamiento, OFF es el nivel de constraint, SDK/ANIM para animacion.
        thigh_fk_off = fk_gens[0].replace("_GRP", "_OFF")
        cmds.parentConstraint(shoulder_driver, thigh_fk_off, mo=True)

        # ---- CONSTRAINTS IK ----
        # ---- CONSTRAINTS CLAVICULE ----
        if self.clavicle:
            cmds.parentConstraint(scapula_top_driver, b_cl_start, mo=True)
            cmds.parentConstraint(shoulder_driver,    c_cl,       mo=True)
        cmds.pointConstraint(ik_root_ctrl,   self.ik_chain[0], mo=True)
        if self.hoof:
            # Reverse hoof:
            #   menudillo (ikH)      -> corona (footBall): FetlockBend / roll l aixeca
            #   cuartilla (footBall) -> lumbre (footTip): queda amb el casc
            #   casc (footTip)       -> hoofCurl: plega el casc sobre la corona
            cmds.parentConstraint(foot_ball_ctrl, ik_h,        mo=True)
            cmds.parentConstraint(foot_tip_ctrl,  ik_footBall, mo=True)
            cmds.parentConstraint(hoof_curl_ctrl, ik_footTip,  mo=True)
        else:
            cmds.parentConstraint(ik_ctrl,       ik_h,             mo=True)  # ✅ ankle IK
            cmds.parentConstraint(foot_ball_ctrl, ik_footBall,     mo=True)  # ball IK
            cmds.parentConstraint(foot_tip_ctrl,  ik_footTip,      mo=True)  # tip IK
        cmds.poleVectorConstraint(pv_ctrl, ik_h)
        #cmds.parentConstraint(clavicule_start_gen, clavicule_ctrl, mo=True)
        if self.clavicle:
            cmds.parentConstraint(shoulder_driver, ik_root_gen, mo=True)
        # (sense clavicula l ik_root_gen es constreny a la pelvis al final)

        if self.three_bone:
            self.build_spring_attrs(ik_ctrl, ik_h)

        # ---- SWITCH atributo + visibilidad ----
        cmds.addAttr(switch_ctrl, ln="IK_FK", at="double", min=0, max=1, k=True)
        cmds.addAttr(switch_ctrl, ln = "Curvature", at="float",min = 0, max=1, dv=0, k =True)

        cmds.parentConstraint(ik_root_ctrl,switch_gen, mo = True )
        vis_rev = cmds.createNode("reverse", n=f"{self.prefix}_VIS_REV")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{self.fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX",   f"{self.ik_grp}.visibility")

        if self.scapula:
            # vis_rev.outputX = 1 en mode IK: l auto nomes actua en IK
            self.build_auto_scapula(clavicule_start_ctrl, clavicule_gen, ik_ctrl,
                                    f"{vis_rev}.outputX", pos_cl_start, pos_cl)

        # ---- PAIR BLENDS ----
        for i in range(len(self.names)):
            pbl_creator = NodeCreator(
                side=self.side,
                node_type="pairBlend",
                base_name=self.prefix,
                name=self.names[i],
                tag="blend",
                parent=None,
                custom_suffix=None
            )
            pbl = pbl_creator.create()
            cmds.setAttr(f"{pbl}.rotInterpolation", 1)
            cmds.connectAttr(f"{self.ik_chain[i]}.translate", f"{pbl}.inTranslate1")
            cmds.connectAttr(f"{self.ik_chain[i]}.rotate",    f"{pbl}.inRotate1")
            cmds.connectAttr(f"{self.fk_chain[i]}.translate", f"{pbl}.inTranslate2")
            cmds.connectAttr(f"{self.fk_chain[i]}.rotate",    f"{pbl}.inRotate2")
            cmds.connectAttr(f"{pbl}.outTranslate",           f"{self.bind_chain[i]}.translate")
            cmds.connectAttr(f"{pbl}.outRotate",              f"{self.bind_chain[i]}.rotate")
            cmds.connectAttr(f"{switch_ctrl}.IK_FK",          f"{pbl}.weight")
            
        
        # ---- FOOT REVERSE ----
        #Separator
        cmds.addAttr(ik_ctrl, ln = "extraAttrSep",nn = "EXTRA_ATTR",at = "enum",en = "------" ,k=False)
        cmds.setAttr(f"{ik_ctrl}.extraAttrSep", cb=True)  
        cmds.setAttr(f"{ik_ctrl}.extraAttrSep", l=True)

        #Roll
        cmds.addAttr(ik_ctrl, ln = "Roll", at="float",k =True)

        #Roll Lift Angle
        cmds.addAttr(ik_ctrl, ln ="RollLiftAngle",k=True, at="float",min = 0, dv =45 )  

        #Roll Straight Angle
        cmds.addAttr(ik_ctrl, ln ="RollStraightAngle", k=True, at="float", min = 0, dv =90 ) 

        cmds.addAttr(ik_ctrl, ln = "Soft", at = "double", min = 0, max = 1, dv = 0, k =True)
        
        
        def quick_node(node_type, name, tag, side="L", base_name="leg", parent=None):
            """Simplifica la instanciación de NodeCreator para evitar código repetitivo."""
            creator = NodeCreator(
                side=side,
                node_type=node_type,
                base_name=base_name,
                name=name,
                tag=tag,
                parent=parent,
                custom_suffix=None
            )
            return creator.create()

        #Creacion de nodos y sus atributos
        heel_clp = quick_node("clamp", "Roll", "Positive")
        cmds.setAttr(f"{heel_clp}.minR",-1080)
        cmds.connectAttr(f"{ik_ctrl}.Roll", f"{heel_clp}.inputR")
        heel_sdk = foot_heel_gen.replace("_GRP", "_SDK")
        cmds.connectAttr(f"{heel_clp}.outputR", f"{heel_sdk}.rotateX")


        legLiftAngle_rmv  = quick_node("remapValue", "RollLift", "Angle")
        cmds.connectAttr(f"{ik_ctrl}.Roll",f"{legLiftAngle_rmv}.inputValue")
        cmds.connectAttr(f"{ik_ctrl}.RollLiftAngle",f"{legLiftAngle_rmv}.inputMax")

        legRollStraightAngle_rmv  = quick_node("remapValue", "straightRoll", "Angle")
        cmds.connectAttr(f"{ik_ctrl}.RollLiftAngle",f"{legRollStraightAngle_rmv}.inputMin")
        cmds.connectAttr(f"{ik_ctrl}.Roll",f"{legRollStraightAngle_rmv}.inputValue")
        cmds.connectAttr(f"{ik_ctrl}.RollStraightAngle",f"{legRollStraightAngle_rmv}.inputMax")

        legRollStraightAngle_rev = quick_node("reverse", "legRollStraight", "Angle")
        cmds.connectAttr(f"{legRollStraightAngle_rmv}.outValue",f"{legRollStraightAngle_rev}.inputX")

        legLiftAngle_mdn = quick_node("multiplyDivide", "legLift", "Angle")
        cmds.connectAttr(f"{legRollStraightAngle_rmv}.outValue",f"{legLiftAngle_mdn}.input1X")
        cmds.connectAttr(f"{ik_ctrl}.Roll",f"{legLiftAngle_mdn}.input2X")

        tip_sdk = foot_tip_gen.replace("_GRP", "_SDK")
        cmds.connectAttr(f"{legLiftAngle_mdn}.outputX",f"{tip_sdk}.rotateX")
   
        legRollStraightAngleBallRange_mdn = quick_node("multiplyDivide", "legRollStraightAngle", "BallRange")
        cmds.connectAttr(f"{legRollStraightAngle_rev}.outputX",f"{legRollStraightAngleBallRange_mdn}.input1X")
        cmds.connectAttr(f"{legLiftAngle_rmv}.outValue",f"{legRollStraightAngleBallRange_mdn}.input2X")

        legRollStraightAngleBall_mdn = quick_node("multiplyDivide", "legRollStraightAngle", "Ball")
        cmds.connectAttr(f"{legRollStraightAngleBallRange_mdn}.outputX",f"{legRollStraightAngleBall_mdn}.input1X")
        cmds.connectAttr(f"{ik_ctrl}.Roll", f"{legRollStraightAngleBall_mdn}.input2X")
        ball_sdk = foot_ball_gen.replace("_GRP", "_SDK")
        cmds.connectAttr(f"{legRollStraightAngleBall_mdn}.outputX", f"{ball_sdk}.rotateX")

        # ---- CASC ----
        if self.hoof:
            self.build_hoof_attrs(
                ik_ctrl=ik_ctrl,
                roll_ball_plug=f"{legRollStraightAngleBall_mdn}.outputX",
                ball_sdk=ball_sdk,
                tip_sdk=tip_sdk,
                bank_in_sdk=foot_bankIn_gen.replace("_GRP", "_SDK"),
                bank_out_sdk=foot_bankOut_gen.replace("_GRP", "_SDK"),
                curl_sdk=hoof_curl_gen.replace("_GRP", "_SDK"),
            )


        # 8. ORGANIZACIÓN FINAL
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.leg_grp, rig_grp)
            cmds.parent(ik_h, ik_footBall, ik_footTip, self.leg_grp)
            if self.clavicle:
                cmds.parent(b_cl_start, self.leg_grp)
            else:
                # sense clavicula les tres cadenes eren al mon: totes al leg_GRP
                cmds.parent(bind_root, self.ik_chain[0], self.fk_chain[0], self.leg_grp)
        cmds.parent(switch_gen, self.main_rig_grp)    
            
        local_ctl = self.root_instance.localCtl if self.root_instance else None

        if local_ctl and cmds.objExists(local_ctl):
            if self.side == "L":
                cmds.parent(self.main_rig_grp, local_ctl)

        # Buscar en la instancia del Hip y NO en el root_instance
        #hipControl = None
        #if hasattr(self, 'hip_instance') and self.hip_instance:
            #if hasattr(self.hip_instance, 'hip_control_name'):
                #hipControl = self.hip_instance.hip_control_name

        # APLICAR EL POINT CONSTRAINT AL HIP CONTROL
        #if hipControl and cmds.objExists(hipControl):
            # Restringimos el grupo principal de controles de la pierna (main_rig_grp) a la cadera
            #cmds.parentConstraint(hipControl, ik_root_gen, mo=True)
            #cmds.parentConstraint(hipControl,fk_gens[0], mo= True )
            #print(f"[{self.prefix}] Vinculado exitosamente mediante pointConstraint a: {hipControl}")
        #else:
            #cmds.warning(f"[{self.prefix}] No se pudo conectar al Hip porque 'hip_control_name' no está disponible.")
        
        

        chestControl = self.clavicule_parent
        
        if cmds.objExists(chestControl):
            # Es mejor restringir el grupo de la clavícula manteniendo el offset
            #cmds.parentConstraint(chestControl, ik_root_gen, mo=True)
            top_gen = clavicule_start_gen if self.clavicle else ik_root_gen
            cmds.parentConstraint(chestControl, top_gen, mo=True)
            print(f"Conectat {top_gen} a {chestControl}.")
        else:
            # Si entra aquí, es porque el pecho no se ha creado todavía en la escena
            print(f"ADVERTENCIA: No se pudo encontrar {chestControl}. Asegúrate de construir el ChestModule ANTES que los Limbs.")

        print(f"Build {self.prefix} completo.")        
        # =========================================================
        # CURVATURA
        # =========================================================

        leg_curvature = curvature_module.CurvatureModule(
            name=f"{self.prefix}_Leg_Curvature",
            side=self.side,
            guide_data=None,
            root_instance=self.root_instance
        )
        leg_curvature.create_basic_curve(
            start_joint    = self.bind_chain[0],
            mid_joint      = self.bind_chain[1],
            end_joint      = self.bind_chain[2],
            switch_control = f"{self.prefix}_switch_CTRL"
        )

        # =========================================================
        # TWIST  ← recibe las curvas ya detacheadas del Curvature
        # =========================================================
        # "leg" per a la cama de davant (noms de sempre); la resta fa servir el
        # rig_name perque el twist de la pota del darrere no xoqui amb el davanter
        twist_name = "leg" if self.rig_name == "Leg" else self.rig_name[0].lower() + self.rig_name[1:]
        leg_twist = twist_module.TwistModule(
            name=twist_name,
            side=self.side,
            parent=self,
            root_instance=self.root_instance
        )
        leg_twist.create_basic_curve(
            self.bind_chain[0],
            self.bind_chain[1],
            self.bind_chain[2],
            aim_axis      = "x",
            up_axis       = "zneg",
            front_axis_idx= 0,
            up_axis_idx   = 2,
            source_curve = leg_curvature.degree2_curve
)


        print(f"Build {self.prefix} leg completo.")
        print(f"Leg Module {self.side} construido con éxito.")