# -*- coding: utf-8 -*-
"""
horse_spine.py - Espina dorsal para caballo (Maya 2026, Python 3)

Rig (completament IK):
  - Dues guies (root i end) creades al guides_module.
  - Curva recta de root a end, de grado 3 con 2 spans = 5 CVs:
        cv0 hip | cv1 hipTangent | cv2 mid | cv3 chestTangent | cv4 chest
  - Un cluster por CV (en systems_GRP) y un control encima de cada cluster
    (GRP > SPC > OFF > SDK > CTRL) con parentConstraint control -> cluster.
  - Jerarquía:  COG > hip   > hipTangent
                COG > chest > chestTangent
                COG > mid   (su SPC sigue 50% a hip y chest)
  - Spline IK con Advanced Twist (controles hip y chest).
  - Stretch con compensación de escala global (atributo en chest_CTRL).
  - Los controles cuelgan del body_CTL (COG), que crea hip_module con su
    pivote movible. build_body=True solo para usar la espina por separado.
  - pelvis_JNT y chest_JNT fuera de la cadena spline.

Integració amb l autorig (build_module):
  - guide_names: els dos joints de guia de CharacterGuides (spine_root, spine_end).
    Aquest modul NO crea guies: les crea guides_module.HorseSpineGuides.
  - root_instance: els joints van a <rig>_rig_GRP i els controls penjen del
    body_CTL (que fa de COG, aixi no es crea un COG duplicat).
  - La mida dels controls s escala segons la llargada real de l espina.
  - attach_control(): fa que chestFix_CTL / localHip_CTL segueixin l espina.

Uso:
    import guides_module, horse_spine
    guides_module.HorseSpineGuides().spine_guides()   # guies
    spine = horse_spine.HorseSpine(name="spine", num_joints=9)
    spine.build()                                      # rig
"""
import maya.cmds as cmds
import maya.api.OpenMaya as om2


class HorseSpine(object):

    # Guies per defecte (joints creats per guides_module.HorseSpineGuides)
    DEFAULT_GUIDES = ("spine_root", "spine_end")
    # Llargada per a la qual estan pensats els radis dels controls (~110 cm)
    REFERENCE_LENGTH = 110.0
    STACK = ("SPC", "OFF", "SDK")   # GRP > SPC > OFF > SDK > CTRL
    CTRL_SUFFIX = "CTRL"

    def __init__(self, name="spine", num_joints=9, up_vector=(0, 1, 0),
                 guide_names=None, root_instance=None, cog_parent=None,
                 build_body=False, body_parent=None):
        if num_joints < 3:
            raise ValueError("num_joints debe ser >= 3")
        guide_names = tuple(guide_names or self.DEFAULT_GUIDES)
        if len(guide_names) != 2:
            raise ValueError("guide_names necesita 2 guias: (root, end)")
        self.name = name
        self.num_joints = num_joints
        self.up = om2.MVector(*up_vector)

        #Guies (root, end) creades al guides_module
        self.guide_names = guide_names
        self.root_instance = root_instance

        #Control del que pengen els controls de l espina. Amb root_instance es
        #el body_CTL, que ja fa de COG.
        if cog_parent is None and root_instance is not None:
            cog_parent = getattr(root_instance, "body_ctl", None)
        self.cog_parent = cog_parent

        #El body (COG) el crea hip_module. Nomes amb build_body=True el crea
        #aquest modul (per fer servir l espina sola, fora de l autorig)
        self.build_body = build_body
        self.body_parent = body_parent      # None -> local_CTL del root
        self.body = None

        #Es calcula al build a partir de la llargada de la curva
        self.scale = 1.0

    # ------------------------------------------------------------------ #
    # GUIES (nomes es llegeixen; es creen al guides_module)
    # ------------------------------------------------------------------ #
    def _guide_positions(self):
        missing = [g for g in self.guide_names if not cmds.objExists(g)]
        if missing:
            raise RuntimeError("[HorseSpine] Falten guies: %s. Crea-les amb "
                               "guides_module abans del build." % missing)
        return [om2.MVector(*cmds.xform(g, q=True, ws=True, t=True))
                for g in self.guide_names]

    # ------------------------------------------------------------------ #
    # HELPERS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _curve_fn(curve):
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        sel = om2.MSelectionList()
        sel.add(shape)
        return om2.MFnNurbsCurve(sel.getDagPath(0)), shape

    @staticmethod
    def _point_at_length(fn, length):
        total = fn.length()
        if length >= total:
            param = fn.knotDomain[1]
        else:
            param = fn.findParamFromLength(max(length, 0.0))
        p = fn.getPointAtParam(param, om2.MSpace.kWorld)
        t = fn.tangent(param, om2.MSpace.kWorld)
        return om2.MVector(p.x, p.y, p.z), om2.MVector(t)

    def _aim_matrix(self, pos, aim_dir):
        """X = aim, Y = up (ortogonalizado), Z = X ^ Y."""
        x = om2.MVector(aim_dir).normal()
        z = (x ^ self.up).normal()
        y = (z ^ x).normal()
        return [x.x, x.y, x.z, 0.0,
                y.x, y.y, y.z, 0.0,
                z.x, z.y, z.z, 0.0,
                pos.x, pos.y, pos.z, 1.0]

    def _joint(self, name, matrix, parent, radius=2.0):
        cmds.select(clear=True)
        jnt = cmds.joint(name=name, radius=radius * self.scale)
        cmds.xform(jnt, ws=True, m=matrix)
        jnt = cmds.parent(jnt, parent)[0]
        # rotación -> jointOrient
        cmds.makeIdentity(jnt, apply=True, t=False, r=True, s=True, n=False)
        return jnt

    def _ctrl_stack(self, name, pos, parent, radius=15.0,
                    normal=(0, 0, 1), color=17, suffix=None):
        radius *= self.scale
        suffix = suffix or self.CTRL_SUFFIX
        grp = cmds.createNode("transform", name=name + "_GRP",
                              **({"parent": parent} if parent else {}))
        cmds.xform(grp, ws=True, t=[pos.x, pos.y, pos.z])
        stack = {"grp": grp}
        last = grp
        for suf in self.STACK:
            last = cmds.createNode("transform", name="%s_%s" % (name, suf),
                                   parent=last)
            stack[suf.lower()] = last
        ctrl = cmds.circle(name="%s_%s" % (name, suffix),
                           nr=normal, r=radius, ch=False)[0]
        ctrl = cmds.parent(ctrl, last, relative=True)[0]
        for shp in cmds.listRelatives(ctrl, shapes=True, fullPath=True) or []:
            cmds.setAttr(shp + ".overrideEnabled", 1)
            cmds.setAttr(shp + ".overrideColor", color)
        for attr in ("sx", "sy", "sz", "v"):
            cmds.setAttr("%s.%s" % (ctrl, attr), lock=True, keyable=False,
                         channelBox=False)
        stack["ctrl"] = ctrl
        return stack

    # ------------------------------------------------------------------ #
    # BODY (COG) AMB PIVOT MOVIBLE
    # ------------------------------------------------------------------ #
    def _build_body(self, pos):
        """
        local_CTL
         └ COGPivot_CTRL          el animador el mou per recol.locar el pivot
           └ COGPivot_NEG         rep la inversa de la MATRIU LOCAL del pivot
             └ body_CTL           d aqui pengen els controls de l espina
               └ bodyOut_TRN      -> parentConstraint -> body_JNT

        Moure el pivot no mou res (el NEG ho cancel.la). Rotar o escalar el
        body ho fa al voltant del punt on s hagi deixat el pivot.
        No es toquen rotatePivot ni scalePivot, aixi que no hi ha desplacaments
        rars quan el body esta rotat.
        """
        rig = self.root_instance.rig_name if self.root_instance else self.name

        body_ctl_name = "%s_body_CTL" % rig
        if cmds.objExists(body_ctl_name):
            cmds.warning("[HorseSpine] %s ja existeix: no es torna a crear."
                         % body_ctl_name)
            return {"ctrl": body_ctl_name}

        parent = self.body_parent
        if parent is None and self.root_instance is not None:
            parent = getattr(self.root_instance, "localCtl", None)
        if parent and not cmds.objExists(parent):
            parent = None

        # Pivot
        pivot = self._ctrl_stack("%s_COGPivot" % rig, pos, parent,
                                 22.0, (0, 1, 0), 18)

        # NEG: cancel.la la matriu local del pivot
        neg = cmds.createNode("transform", name="%s_COGPivot_NEG" % rig,
                              parent=pivot["ctrl"])
        inv = cmds.createNode("inverseMatrix", name="%s_COGPivot_IMX" % rig)
        cmds.connectAttr(pivot["ctrl"] + ".matrix", inv + ".inputMatrix")
        cmds.connectAttr(inv + ".outputMatrix", neg + ".offsetParentMatrix")

        # Body (COG)
        body = self._ctrl_stack("%s_body" % rig, pos, neg,
                                45.0, (0, 1, 0), 17, suffix="CTL")

        # Sortida per al joint: filla del body i en identitat, aixi no li
        # afecta res del pivot
        out = cmds.createNode("transform", name="%s_bodyOut_TRN" % rig,
                              parent=body["ctrl"])

        cmds.select(clear=True)
        jnt = cmds.joint(name="%s_body_JNT" % rig,
                         p=[pos.x, pos.y, pos.z],
                         radius=3.0 * self.scale)
        cmds.select(clear=True)
        rig_grp = "%s_rig_GRP" % rig
        if cmds.objExists(rig_grp):
            jnt = cmds.parent(jnt, rig_grp)[0]
        cmds.parentConstraint(out, jnt, mo=True, name="%s_body_PAC" % rig)

        if self.root_instance is not None:
            self.root_instance.body_ctl = body["ctrl"]

        self.body = {"pivot": pivot, "neg": neg, "ctrl": body["ctrl"],
                     "stack": body, "out": out, "joint": jnt}
        return self.body

    # ------------------------------------------------------------------ #
    # BUILD
    # ------------------------------------------------------------------ #
    def build(self):
        n = self.name
        if cmds.objExists(n + "_module_GRP"):
            raise RuntimeError("Ya existe %s_module_GRP" % n)

        cmds.undoInfo(openChunk=True)
        try:
            return self._build(n)
        finally:
            cmds.undoInfo(closeChunk=True)

    def _build(self, n):
        positions = self._guide_positions()

        # --- Jerarquía del módulo ----------------------------------------
        module = cmds.createNode("transform", name=n + "_module_GRP")
        ctrls_grp = cmds.createNode("transform", name=n + "_controls_GRP", parent=module)
        jnts_grp = cmds.createNode("transform", name=n + "_joints_GRP", parent=module)
        sys_grp = cmds.createNode("transform", name=n + "_systems_GRP", parent=module)
        cmds.setAttr(sys_grp + ".inheritsTransform", 0)
        cmds.setAttr(sys_grp + ".visibility", 0)

        # --- Curva de 5 CVs (grau 3, 2 spans) -----------------------------
        # Recta de root a end amb els CVs repartits a parts iguals:
        # hip, tangent hip, mid, tangent chest, chest.
        root_pos, end_pos = positions
        if (end_pos - root_pos).length() < 0.0001:
            raise RuntimeError("[HorseSpine] root i end estan al mateix punt")
        cv_pos = [root_pos + (end_pos - root_pos) * (k / 4.0) for k in range(5)]

        crv = cmds.curve(d=3, p=[(p.x, p.y, p.z) for p in cv_pos], name=n + "_ik_CRV")
        fn, crv_shape = self._curve_fn(crv)
        total = fn.length()

        #Els radis estan pensats per a una espina de ~110 cm.
        #Si l escena te una altra escala, els controls s adapten.
        self.scale = total / self.REFERENCE_LENGTH

        # --- Punts i matrius de la cadena ---------------------------------
        pts = []
        for i in range(self.num_joints):
            p, _ = self._point_at_length(fn, total * i / float(self.num_joints - 1))
            pts.append(p)
        mats = []
        for i, p in enumerate(pts):
            aim = (pts[i + 1] - p) if i < len(pts) - 1 else (p - pts[i - 1])
            mats.append(self._aim_matrix(p, aim))

        # --- Joints ------------------------------------------------------
        joints = []
        parent = jnts_grp
        for i, m in enumerate(mats):
            j = self._joint("%s%02d_JNT" % (n, i + 1), m, parent)
            joints.append(j)
            parent = j

        pelvis_jnt = self._joint(n + "_pelvis_JNT", mats[0], jnts_grp, 3.0)
        chest_jnt = self._joint(n + "_chest_JNT", mats[-1], joints[-1], 3.0)

        # --- Clusters (un per CV) -----------------------------------------
        cv_names = ["hip", "hipTangent", "mid", "chestTangent", "chest"]
        clusters = {}
        for k, key in enumerate(cv_names):
            handle = cmds.cluster("%s.cv[%d]" % (crv, k), name="%s_%s_CLS" % (n, key))[1]
            clusters[key] = cmds.parent(handle, sys_grp)[0]
        crv = cmds.parent(crv, sys_grp)[0]
        fn, crv_shape = self._curve_fn(crv)

        # --- Body (COG) amb pivot movible ---------------------------------
        if self.build_body:
            self._build_body(cv_pos[0])
            if self.body:
                self.cog_parent = self.body["ctrl"]

        # --- Controles ---------------------------------------------------
        if self.cog_parent and cmds.objExists(self.cog_parent):
            #El body_CTL de l autorig ja fa de COG: no se n crea un altre
            cog = {"ctrl": ctrls_grp}
        else:
            cog = self._ctrl_stack(n + "_COG", cv_pos[0], ctrls_grp, 45.0, (0, 1, 0), 22)

        hip = self._ctrl_stack(n + "_hip", cv_pos[0], cog["ctrl"], 28.0, (0, 0, 1), 17)
        chest = self._ctrl_stack(n + "_chest", cv_pos[4], cog["ctrl"], 28.0, (0, 0, 1), 17)
        mid = self._ctrl_stack(n + "_mid", cv_pos[2], cog["ctrl"], 22.0, (0, 0, 1), 20)

        # Tangents: sota el control principal mes proper
        hip_tan = self._ctrl_stack(n + "_hipTangent", cv_pos[1], hip["ctrl"], 16.0, (0, 0, 1), 18)
        chest_tan = self._ctrl_stack(n + "_chestTangent", cv_pos[3], chest["ctrl"], 16.0, (0, 0, 1), 18)

        # El mid segueix a mitges hip i chest (es pot animar a sobre)
        cmds.parentConstraint(hip["ctrl"], chest["ctrl"], mid["spc"], mo=True,
                              name=n + "_mid_SPC_PAC")

        # --- Control -> cluster --------------------------------------------
        ctrl_by_cv = {"hip": hip, "hipTangent": hip_tan, "mid": mid,
                      "chestTangent": chest_tan, "chest": chest}
        for key in cv_names:
            cmds.parentConstraint(ctrl_by_cv[key]["ctrl"], clusters[key], mo=True,
                                  name="%s_%s_CLS_PAC" % (n, key))

        # --- Spline IK + Advanced Twist ----------------------------------
        ik = cmds.ikHandle(name=n + "_IKH", sj=joints[0], ee=joints[-1],
                           c=crv_shape, sol="ikSplineSolver",
                           ccv=False, pcv=False)[0]
        cmds.parent(ik, sys_grp)
        cmds.setAttr(ik + ".dTwistControlEnable", 1)
        cmds.setAttr(ik + ".dWorldUpType", 4)        # Object Rotation Up (Start/End)
        cmds.setAttr(ik + ".dForwardAxis", 0)        # +X
        cmds.setAttr(ik + ".dWorldUpAxis", 0)        # +Y
        cmds.setAttr(ik + ".dWorldUpVector", 0, 1, 0, type="double3")
        cmds.setAttr(ik + ".dWorldUpVectorEnd", 0, 1, 0, type="double3")
        cmds.connectAttr(hip["ctrl"] + ".worldMatrix[0]", ik + ".dWorldUpMatrix")
        cmds.connectAttr(chest["ctrl"] + ".worldMatrix[0]", ik + ".dWorldUpMatrixEnd")

        # --- Stretch con escala global -----------------------------------
        cmds.addAttr(chest["ctrl"], ln="stretch", at="double",
                     min=0, max=1, dv=1, k=True)
        cin = cmds.createNode("curveInfo", name=n + "_ik_CIN")
        cmds.connectAttr(crv_shape + ".worldSpace[0]", cin + ".inputCurve")

        dcm = cmds.createNode("decomposeMatrix", name=n + "_globalScale_DCM")
        cmds.connectAttr(module + ".worldMatrix[0]", dcm + ".inputMatrix")
        rest = cmds.createNode("multDoubleLinear", name=n + "_restLength_MDL")
        cmds.setAttr(rest + ".input1", total)
        cmds.connectAttr(dcm + ".outputScaleX", rest + ".input2")

        ratio = cmds.createNode("multiplyDivide", name=n + "_stretchRatio_MDV")
        cmds.setAttr(ratio + ".operation", 2)
        cmds.connectAttr(cin + ".arcLength", ratio + ".input1X")
        cmds.connectAttr(rest + ".output", ratio + ".input2X")

        bta = cmds.createNode("blendTwoAttr", name=n + "_stretch_BTA")
        cmds.setAttr(bta + ".input[0]", 1.0)
        cmds.connectAttr(ratio + ".outputX", bta + ".input[1]")
        cmds.connectAttr(chest["ctrl"] + ".stretch", bta + ".attributesBlender")

        for j in joints[1:]:
            mdl = cmds.createNode("multDoubleLinear", name=j.replace("_JNT", "_stretch_MDL"))
            cmds.setAttr(mdl + ".input1", cmds.getAttr(j + ".translateX"))
            cmds.connectAttr(bta + ".output", mdl + ".input2")
            cmds.connectAttr(mdl + ".output", j + ".translateX")

        # --- Pelvis y pecho fuera del spline -----------------------------
        # pelvis i pit segueixen NOMES els seus controls (posicio i rotacio).
        # El pit abans nomes rotava amb el control i la posicio la treia del
        # final del spline, que es desplaca una mica quan es mou el mid:
        # per aixo les cames de davant es movien.
        cmds.parentConstraint(hip["ctrl"], pelvis_jnt, mo=True, name=n + "_pelvis_PAC")
        cmds.parentConstraint(chest["ctrl"], chest_jnt, mo=True, name=n + "_chest_PAC")

        # --- Integracio amb l autorig -------------------------------------
        if self.root_instance is not None:
            rig_grp = "%s_rig_GRP" % self.root_instance.rig_name
            if cmds.objExists(rig_grp):
                module = cmds.parent(module, rig_grp)[0]
        if self.cog_parent and cmds.objExists(self.cog_parent):
            ctrls_grp = cmds.parent(ctrls_grp, self.cog_parent)[0]

        cmds.select(cog["ctrl"])

        self.data = {
            "module": module, "joints": joints, "pelvis": pelvis_jnt,
            "chest_jnt": chest_jnt, "ik": ik, "curve": crv,
            "clusters": clusters,
            "body": self.body,
            "controls": {"cog": cog, "hip": hip, "hipTangent": hip_tan,
                         "mid": mid, "chestTangent": chest_tan, "chest": chest},
        }
        return self.data

    # ------------------------------------------------------------------ #
    # INTEGRACIO
    # ------------------------------------------------------------------ #
    def attach_control(self, driver, ctl, stop_at=None):
        """
        Fa que un control d un altre modul (chestFix_CTL, localHip_CTL...)
        segueixi un control de l espina.

        Es constreny el primer pare del control que tingui translate/rotate
        lliures (sense connexions ni locks), mantenint l offset. Aixi el
        control segueix sent animable i no cal saber com es diuen els grups
        del chest_module o del hip_module.

        Args:
            driver (str): control de l espina (p.ex. data["controls"]["chest"]["ctrl"])
            ctl (str): control a enganxar
            stop_at (str): no pujar mes amunt d aquest node (per defecte el COG)
        """
        stop_at = stop_at or self.cog_parent
        if not cmds.objExists(ctl):
            cmds.warning("[HorseSpine] No existeix %s, no s enganxa." % ctl)
            return None

        attrs = ("tx", "ty", "tz", "rx", "ry", "rz")
        node = ctl
        for _ in range(4):   #nomes els grups d offset propers, mai grups grans
            parents = cmds.listRelatives(node, parent=True)
            if (not parents or parents[0] == stop_at
                    or parents[0].endswith(("_CTL", "_CTRL"))):
                cmds.warning("[HorseSpine] %s no te cap pare lliure per "
                             "constrenyer." % ctl)
                return None
            node = parents[0]
            busy = any(cmds.listConnections("%s.%s" % (node, a), s=True, d=False)
                       or cmds.getAttr("%s.%s" % (node, a), lock=True)
                       for a in attrs)
            if not busy:
                break
        else:
            cmds.warning("[HorseSpine] %s: cap grup d offset lliure a prop." % ctl)
            return None

        cns = cmds.parentConstraint(driver, node, mo=True,
                                    name="%s_follow_PAC" % node)[0]
        print("[HorseSpine] %s segueix %s (via %s)" % (ctl, driver, node))
        return cns