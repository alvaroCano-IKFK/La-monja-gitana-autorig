import math
import maya.cmds as cmds
import controlsLibrary
from groups_module import ControlsGroups


# ---------------------------------------------------------------------------
# PESOS DEL SKIN DE LA NURBS (fets a ma i exportats amb export_neck_weights.py)
#
# Una fila per cada fila de CVs al llarg de V (de la base al cap) i, dins de
# cada fila, un tuple per cada CV en U:  (pes base, pes mig, pes final).
# Si es None o no quadra amb la NURBS, es fa servir el repartiment lineal.
# ---------------------------------------------------------------------------
NECK_SKIN_WEIGHTS = None


class HorseNeck(object):
    """
    Coll del caball amb RIBBON (NURBS).

    Guies (guides_module.HorseNeckGuides): neck_root -> neck_mid -> neck_end

    Build:
      1. NURBS que ocupa tota la guia:
            U = amplada, 1 span grau 2   -> 3 CVs (vora, centre, vora)
            V = llargada, 2 spans grau 3 -> 5 CVs
      2. 2 joints propis del coll, base i mig. El del mig va al CENTRE DE LA
         NURBS (V 0.5), no a la guia: la guia no cau al mig del parametre.
      3. 2 controls, cadascun amb parentConstraint al seu joint.

         control -> joint -> skinCluster -> NURBS

      4. Cap: un joint i un control (head=True). NO hi ha neckEnd: el cap
         ocupa el seu lloc i el seu joint es la TERCERA influencia de la
         NURBS, o sigui que moure el cap deforma el ribbon.
      5. pin_joints: joints extra enganxats a la superficie amb un uvPin,
         repartits uniformement per la V pero SENSE tocar els extrems. Amb
         els 7 de per defecte, i comptant la ranura de la tangent, van de
         V 0.111 a V 0.778.
      6. tangent_joint: un joint NORMAL (no pin) que porta la fila de CVs de
         la tangent del cap, amb control propi penjat del head_CTRL. Ocupa el
         lloc que abans tenia l ultim pin i serveix per retocar la forma del
         coll just darrere del cap.

    SKIN DE LA NURBS
    ----------------
    Files dures, sense degradat: cada fila de CVs al 100% d un sol joint.

        punta del cap      -> head_JNT
        la seva tangent    -> neckTangent_JNT
        fila del centre    -> neckMid_JNT
        l altra punta i
        la seva tangent    -> neckBase_JNT

    Quina punta es el cap i quina la base no es dona per suposat: pel mig hi
    ha un reverseSurface, aixi que V=0 pot ser qualsevol de les dues. Es mira
    quin joint cau mes a prop del punt V=0 (_head_at_v0).

    EL CAP MANA (head_world_space=True, per defecte)
    ------------------------------------------------
    El control del cap viu en espai de mon, al costat dels controls del
    coll, i nomes segueix el pit (parent_joint). Son els controls del coll
    els que el segueixen a ell: el GRUP D OFFSET de cada control te un
    parentConstraint amb dos targets, el pit i el cap, amb els pesos de
    neck_follow:

        neckBase_OFF   pit 1.0   cap 0.0     -> es queda amb el cos
        neckMid_OFF    pit 0.5   cap 0.5     -> interpola

    Per aixo els controls queden PLANS (tots sota neckControls_GRP) i no en
    cadena: si hi hagues jerarquia, el constraint del grup d offset i la
    transformacio heretada del pare se sumarien (doble transformacio).
    Cada control segueix donant el seu offset manual a sobre del blend.

    Amb head_world_space=False es torna al muntatge antic: cadena
    neckBase > neckMid i el cap penjat de l ultim control del coll.
    """

    #: Els controls i joints PROPIS del coll. El tercer (neckEnd) ja no hi
    #: es: el seu lloc el fa el cap, que deforma la NURBS com un mes.
    NECK_NAMES = ("neckBase", "neckMid")

    def __init__(self,
                 root_guide="neck_root",
                 mid_guide="neck_mid",
                 end_guide="neck_end",
                 rig_name="Character",
                 v_spans=2,
                 v_degree=3,
                 u_spans=1,
                 u_degree=2,
                 pin_joints=7,
                 tangent_joint=True,
                 mid_on_surface=True,
                 head=True,
                 head_guide=None,
                 head_world_space=True,
                 neck_follow=(0.0, 0.5),
                 aim_at_head=True,
                 aim_vector=(1, 0, 0),
                 aim_up_vector=(0, 0, 1),
                 width=None,
                 parent_joint=None,
                 root_instance=None,
                 skin_weights=None):
        self.guides = [root_guide, mid_guide, end_guide]
        self.rig_name = rig_name
        self.v_spans = v_spans
        self.v_degree = v_degree
        self.u_spans = u_spans
        self.u_degree = u_degree
        self.pin_joints = pin_joints
        # Joint NORMAL (no pin) que porta la fila de CVs de la tangent del
        # cap, amb control propi penjat del head_CTRL per retocar la forma
        self.tangent_joint = tangent_joint
        # El joint del mig, al centre de la NURBS (V 0.5) i no a la guia
        self.mid_on_surface = mid_on_surface
        #Cap: joint i control al final del coll. head_guide=None -> la guia
        #del final del coll (neck_end)
        self.head = head
        self.head_guide = head_guide
        # El cap en espai de mon i els controls del coll seguint-lo
        self.head_world_space = head_world_space
        # Quant segueix el cap cada control del coll (base, mig).
        # La resta fins a 1.0 se la queda el pit (parent_joint).
        self.neck_follow = tuple(neck_follow)
        # aimConstraint de cada control del coll al control del cap
        self.aim_at_head = aim_at_head
        self.aim_vector = tuple(aim_vector)
        # L up i el world up de l aim. Z en tots dos: el coll es al pla
        # sagital, aixi que la Z es l eix que no li fa fer la campana.
        self.aim_up_vector = tuple(aim_up_vector)
        self.width = width            # None -> 10% de la llargada del coll
        self.parent_joint = parent_joint
        self.root_instance = root_instance
        # Pesos a ma: el parametre te prioritat sobre NECK_SKIN_WEIGHTS
        self.skin_weights = skin_weights if skin_weights is not None else NECK_SKIN_WEIGHTS

        self.ctrl_style = "circleControl"
        self.group_maker = ControlsGroups()

        self.surface = None
        self.joints = []        # els joints propis del coll (base, mig)
        self.controls = []
        self.pinned = []        # joints extra enganxats amb uvPin (opcional)
        self.uv_pin = None
        self.head_joint = None
        self.head_ctrl = None
        self.tangent_jnt = None     # joint de la tangent del cap
        self.tangent_ctrl = None
        self.tops = []          # el grup de dalt de cada control del coll
        self.offsets = []       # el grup d offset de cada control del coll
        self.aims = []          # els aimConstraint al cap

    # ------------------------------------------------------------------ #
    # HELPERS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sub(a, b):
        return [a[i] - b[i] for i in range(3)]

    @staticmethod
    def _dot(a, b):
        return sum(a[i] * b[i] for i in range(3))

    @staticmethod
    def _length(a):
        return math.sqrt(sum(v * v for v in a))

    @staticmethod
    def _offset_group(top, ctrl):
        """
        El grup d OFFSET de la pila GRP > SPC > OFF > SDK > CTRL.

        Es baixa del grup de dalt fins al control buscant el node que acaba
        en _OFF. Si la pila canvia de noms es torna el grup de dalt, que
        funciona igual (nomes es perd el nivell d offset per a l animador).
        """
        node = top
        while node and node != ctrl:
            if node.split("|")[-1].upper().endswith("_OFF"):
                return node
            children = cmds.listRelatives(node, c=True, type="transform",
                                          fullPath=False) or []
            node = children[0] if children else None
        return top

    @staticmethod
    def _world_axes(node):
        m = cmds.xform(node, q=True, ws=True, m=True)
        return m[0:3], m[4:7], m[12:15]   # X, Y, posicio

    # ------------------------------------------------------------------ #
    # 1. NURBS
    # ------------------------------------------------------------------ #
    def _build_surface(self, guide_pos, parent):
        n = self.rig_name
        seg_a = self._length(self._sub(guide_pos[1], guide_pos[0]))
        seg_b = self._length(self._sub(guide_pos[2], guide_pos[1]))
        width = self.width or (seg_a + seg_b) * 0.1

        # Tres corbes paral.leles per les guies (el coll es al pla sagital,
        # l amplada va en X del mon): esquerra, centre, dreta
        curves = []
        for offset in (-width * 0.5, 0.0, width * 0.5):
            pts = [(p[0] + offset, p[1], p[2]) for p in guide_pos]
            curves.append(cmds.curve(ep=pts, d=3))

        surf = cmds.loft(curves, ch=False, u=True, c=False, ar=True, d=1,
                         ss=1, rn=False, po=0, rsn=True,
                         n=f"{n}_neckRibbon_NRB")[0]
        cmds.delete(curves)

        # El loft deixa U al llarg de les corbes: s intercanvien U i V
        # perque U sigui l amplada i V la llargada
        cmds.reverseSurface(surf, d=3, ch=False, rpo=True)

        # U: 1 span grau 2 | V: 2 spans grau 3 | rang 0-1 en tots dos
        cmds.rebuildSurface(surf, ch=False, rpo=True, rt=0, end=1, kr=0,
                            kcp=False, kc=False,
                            su=self.u_spans, du=self.u_degree,
                            sv=self.v_spans, dv=self.v_degree,
                            tol=0.01, fr=0, dir=2)

        self.surface = cmds.parent(surf, parent)[0]
        return self.surface, seg_a / (seg_a + seg_b)

    # ------------------------------------------------------------------ #
    # 2. JOINTS + SKIN
    # ------------------------------------------------------------------ #
    def _surface_point(self, u, v):
        """
        Posicio al mon d un punt de la NURBS, amb els parametres de 0 a 1.

        pointOnSurface torna el punt en l espai de l objecte, aixi que es
        multiplica per la worldMatrix de la superficie. Ara mateix la
        superficie esta en identitat i seria el mateix, pero si algun dia
        penja d un grup mogut, aixo segueix sent correcte.
        """
        p = cmds.pointOnSurface(self.surface, u=u, v=v, position=True)
        m = cmds.xform(self.surface, q=True, ws=True, m=True)

        return [p[0] * m[0] + p[1] * m[4] + p[2] * m[8] + m[12],
                p[0] * m[1] + p[1] * m[5] + p[2] * m[9] + m[13],
                p[0] * m[2] + p[1] * m[6] + p[2] * m[10] + m[14]]

    def _cv_count(self):
        """Quants CVs te la NURBS en U i en V."""
        shape = cmds.listRelatives(self.surface, s=True, f=True)[0]
        return (cmds.getAttr(f"{shape}.spansU") + cmds.getAttr(f"{shape}.degreeU"),
                cmds.getAttr(f"{shape}.spansV") + cmds.getAttr(f"{shape}.degreeV"))

    def _head_at_v0(self):
        """
        True si la punta V=0 de la NURBS es la del cap.

        No es pot donar per suposat: pel mig hi ha un reverseSurface i, segons
        com quedi, V=0 pot ser el cap o la base. Es mira quin dels dos joints
        cau mes a prop del punt V=0.
        """
        if not (self.head_joint and cmds.objExists(self.head_joint)):
            return False

        start = self._surface_point(0.5, 0.0)
        to_head = self._length(self._sub(
            cmds.xform(self.head_joint, q=True, ws=True, t=True), start))
        to_base = self._length(self._sub(
            cmds.xform(self.joints[0], q=True, ws=True, t=True), start))

        return to_head < to_base

    def _cv_row_center(self, v):
        """El centre de la fila de CVs v, en espai de mon."""
        num_u, _ = self._cv_count()
        points = [cmds.xform(f"{self.surface}.cv[{u}][{v}]", q=True, ws=True, t=True)
                  for u in range(num_u)]

        return [sum(p[i] for p in points) / float(len(points)) for i in range(3)]

    def _build_tangent_joint(self, jnt_parent):
        """
        Joint i control de la TANGENT del cap.

        Ocupa el lloc que abans tenia l ultim uvPin, pero no es un pin: es un
        joint normal, influencia del mateix skinCluster, que porta la fila de
        CVs de la tangent del cap. El seu control penja del head_CTRL, aixi
        que acompanya el cap pero es pot moure a part per retocar la forma
        del coll just darrere del cap.

        Va al CENTRE DE LA FILA DE CVs que deforma, no sobre la superficie:
        els CVs de la tangent no toquen la NURBS, i el que ha de moure son
        ells.
        """
        n = self.rig_name
        if not (self.head_ctrl and self.head_joint):
            cmds.warning("[HorseNeck] Sense cap: no es crea el joint de la "
                         "tangent.")
            return None

        _, num_v = self._cv_count()
        row = 1 if self._head_at_v0() else num_v - 2

        cmds.select(clear=True)
        jnt = cmds.joint(n=f"{n}_neckTangent_JNT", p=self._cv_row_center(row))
        cmds.makeIdentity(jnt, apply=True, t=0, r=1, s=0, n=0)
        jnt = cmds.parent(jnt, jnt_parent)[0]
        cmds.select(clear=True)

        ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.ctrl_style,
            final_name=f"{n}_neckTangent_CTRL")
        top = self.group_maker.create_rig_hierarchy(ctrl, jnt)
        cmds.parent(top, self.head_ctrl)
        cmds.parentConstraint(ctrl, jnt, mo=True, n=f"{jnt}_PAC")

        self.tangent_jnt = jnt
        self.tangent_ctrl = ctrl
        print(f"[HorseNeck] Tangent del cap: {jnt} porta la fila de CVs {row}.")
        return jnt

    def _build_joints(self, guide_pos, parent):
        """
        Els joints PROPIS del coll: base i mig. Deformen la NURBS.

        El tercer joint (neckEnd) ja no existeix: el seu lloc el fa el joint
        del cap, que es una influencia mes del mateix skinCluster. Aqui
        encara se n crea un al final, pero nomes per ORIENTAR el del mig al
        llarg del coll; tot seguit s esborra.
        """
        n = self.rig_name
        names = list(self.NECK_NAMES)

        # El del mig va al CENTRE DE LA NURBS (U 0.5, V 0.5), no a la guia.
        # La guia del mig no cau al centre del parametre: la corba passa per
        # tres punts i, si els dos trams no fan el mateix, el mig del
        # parametre queda desplacat respecte de la guia. Com que el joint ha
        # de deformar la superficie, el que mana es la superficie.
        positions = list(guide_pos)
        if self.mid_on_surface and self.surface:
            positions[1] = self._surface_point(0.5, 0.5)

        # Cadena temporal per orientar-los al llarg del coll; despres se separen
        cmds.select(clear=True)
        chain = []
        for i, p in enumerate(positions):
            label = names[i] if i < len(names) else "neckOrientTip_TMP"
            chain.append(cmds.joint(p=p, n=f"{n}_{label}_JNT"))
        cmds.joint(chain[0], e=True, oj="xyz", sao="yup", ch=True, zso=True)
        cmds.setAttr(f"{chain[-1]}.jointOrient", 0, 0, 0)
        cmds.select(clear=True)

        # Fora el de la punta: ja ha fet la seva feina orientant el del mig
        extra = chain[len(names):]
        if extra:
            cmds.delete(extra[0])
        chain = chain[:len(names)]

        self.joints = []
        for jnt in reversed(chain):
            self.joints.insert(0, cmds.parent(jnt, parent)[0])
        return self.joints

    def _skin_surface(self, mid_ratio=None):
        """
        Skin de la NURBS amb tres influencies: base, mig i CAP.

        Res de degradats: cada fila de CVs va a un sol joint al 100%.

            fila 0 i 1          -> el joint d aquella punta
            files del mig       -> neckMid_JNT
            files N-2 i N-1     -> el joint de l altra punta

        O sigui que la punta i la seva TANGENT van juntes al mateix joint:
        amb la tangent lligada al mateix que la punta, el tros final de la
        NURBS acompanya el cap rigid i no se li arrufa.

        Quina punta es el cap i quina la base no es dona per suposat: segons
        com hagi quedat la superficie (hi ha un reverseSurface pel mig), V=0
        pot ser qualsevol de les dues. Es mira quin joint cau mes a prop del
        punt V=0 i es reparteix a partir d aqui.
        """
        n = self.rig_name

        drivers = list(self.joints)                 # base, mig
        if self.head_joint and cmds.objExists(self.head_joint):
            drivers.append(self.head_joint)         # ... el cap
        else:
            cmds.warning("[HorseNeck] Sense joint de cap: la NURBS es queda "
                         "amb els joints del coll.")
        if self.tangent_jnt and cmds.objExists(self.tangent_jnt):
            drivers.append(self.tangent_jnt)        # ... i la seva tangent

        skin = cmds.skinCluster(drivers, self.surface, tsb=True, mi=2,
                                n=f"{n}_neckRibbon_SKC")[0]
        cmds.setAttr(f"{skin}.normalizeWeights", 0)

        shape = cmds.listRelatives(self.surface, s=True, f=True)[0]
        num_u = cmds.getAttr(f"{shape}.spansU") + cmds.getAttr(f"{shape}.degreeU")
        num_v = cmds.getAttr(f"{shape}.spansV") + cmds.getAttr(f"{shape}.degreeV")

        # 1) Pesos fets a ma, si n hi ha i quadren amb la NURBS
        table = self.skin_weights
        if table is not None:
            # Cada casella de la taula porta un pes per influencia, en el
            # mateix ordre que drivers: base, mig, cap i (si hi es) tangent.
            if (len(table) == num_v
                    and all(len(row) == num_u for row in table)
                    and all(len(cell) == len(drivers) for row in table for cell in row)):
                for v, row in enumerate(table):
                    for u, cell in enumerate(row):
                        cmds.skinPercent(skin, f"{self.surface}.cv[{u}][{v}]",
                                         tv=list(zip(drivers, cell)))
                cmds.setAttr(f"{skin}.normalizeWeights", 1)
                print("[HorseNeck] Pesos del ribbon aplicats des de la taula.")
                return skin
            cmds.warning(f"[HorseNeck] La taula de pesos no quadra amb la NURBS "
                         f"({num_v} files x {num_u} CVs x {len(drivers)} "
                         f"influencies). Es fa servir el dur.")

        # 2) Quina fila va a quin joint
        base_jnt = self.joints[0]
        mid_jnt = self.joints[1] if len(self.joints) > 1 else self.joints[0]
        head_jnt = self.head_joint if self.head_joint in drivers else base_jnt

        head_at_v0 = self._head_at_v0()
        head_row = 0 if head_at_v0 else num_v - 1          # la punta del cap
        head_tangent_row = 1 if head_at_v0 else num_v - 2  # la seva tangent

        row_driver = {}
        for v in range(num_v):
            if v == head_row:
                row_driver[v] = head_jnt
            elif v == head_tangent_row:
                # La tangent del cap te joint propi, si s ha creat; si no,
                # se la queda el cap com abans.
                row_driver[v] = self.tangent_jnt or head_jnt
            elif v <= 1 or v >= num_v - 2:
                row_driver[v] = base_jnt          # l altra punta i la seva tangent
            else:
                row_driver[v] = mid_jnt           # el centre

        # 3) Una fila, un joint, al 100%
        for v in range(num_v):
            driver = row_driver[v]
            weights = [(jnt, 1.0 if jnt == driver else 0.0) for jnt in drivers]
            for u in range(num_u):
                cmds.skinPercent(skin, f"{self.surface}.cv[{u}][{v}]", tv=weights)

        cmds.setAttr(f"{skin}.normalizeWeights", 1)
        for v in range(num_v):
            print(f"[HorseNeck] CVs V{v} -> {row_driver[v]}")
        return skin

    # ------------------------------------------------------------------ #
    # 3. CONTROLS
    # ------------------------------------------------------------------ #
    def _build_controls(self, ctrl_grp):
        n = self.rig_name
        names = list(self.NECK_NAMES)
        tops = []
        self.controls = []
        for name, drv in zip(names, self.joints):
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.ctrl_style,
                final_name=f"{n}_{name}_CTRL"
            )
            tops.append(self.group_maker.create_rig_hierarchy(ctrl, drv))
            self.controls.append(ctrl)

        if self.head_world_space:
            # Plans: el blend pit/cap va al grup d offset de cadascun i una
            # jerarquia per sobre hi sumaria una segona transformacio.
            for top in tops:
                cmds.parent(top, ctrl_grp)
        else:
            # Muntatge antic: cadena base > mig
            cmds.parent(tops[0], ctrl_grp)
            for top, parent_ctrl in zip(tops[1:], self.controls[:-1]):
                cmds.parent(top, parent_ctrl)

        for ctrl, drv in zip(self.controls, self.joints):
            cmds.parentConstraint(ctrl, drv, mo=True, n=f"{drv}_PAC")

        self.tops = tops
        self.offsets = [self._offset_group(top, ctrl)
                        for top, ctrl in zip(tops, self.controls)]
        return tops

    # ------------------------------------------------------------------ #
    # 4. CAP
    # ------------------------------------------------------------------ #
    def _build_head(self, parent_ctrl, jnt_parent):
        """
        Joint i control del cap, al final del coll.

        Amb head_world_space el control va en espai de mon (parent_ctrl es el
        grup de controls del coll) i nomes segueix el pit: es ell qui mana i
        els controls del coll el segueixen. Sense, penja de l ultim control
        del coll. El joint del cap deforma la NURBS com els del coll: es la
        influencia que porta la punta del ribbon.

        El joint i el control neixen ALINEATS AMB EL MON, no amb el coll: els
        seus eixos son els del mon i no la direccio de l espina, aixi que el
        cap no te la mateixa rotacio que els controls del coll.
        """
        n = self.rig_name
        guide = self.head_guide if self.head_guide else self.guides[-1]
        if not cmds.objExists(guide):
            cmds.warning(f"[HorseNeck] No existeix {guide}: cap no creat.")
            return None

        # EN ESPAI DE MON: nomes la posicio de la guia. El joint NO copia
        # la rotacio del darrer joint del coll (abans hi havia un
        # matchTransform rot=True): si la copiava, el cap quedava alineat amb
        # la direccio de l espina enlloc de mirar endavant, i el control
        # heretava la mateixa rotacio que els del coll.
        cmds.select(clear=True)
        head_jnt = cmds.joint(n=f"{n}_head_JNT",
                              p=cmds.xform(guide, q=True, ws=True, t=True))
        cmds.makeIdentity(head_jnt, apply=True, t=0, r=1, s=0, n=0)
        head_jnt = cmds.parent(head_jnt, jnt_parent)[0]
        cmds.select(clear=True)

        head_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.ctrl_style,
            final_name=f"{n}_head_CTRL"
        )
        top = self.group_maker.create_rig_hierarchy(head_ctrl, head_jnt)
        cmds.parent(top, parent_ctrl)
        cmds.parentConstraint(head_ctrl, head_jnt, mo=True, n=f"{head_jnt}_PAC")

        # En espai de mon el cap no hereta res del coll: perque acompanyi el
        # cos se l penja del pit amb un constraint al seu grup de dalt.
        if self.head_world_space:
            if self.parent_joint and cmds.objExists(self.parent_joint):
                cmds.parentConstraint(self.parent_joint, top, mo=True,
                                      n=f"{n}_head_follow_PAC")
            else:
                cmds.warning("[HorseNeck] El cap queda en mon pur: no hi ha "
                             "res per seguir el cos.")

        self.head_joint = head_jnt
        self.head_ctrl = head_ctrl
        return head_ctrl

    def _link_neck_to_head(self):
        """
        El blend pit/cap al grup d offset de cada control del coll.

        Un sol parentConstraint per control amb els dos targets: el pes del
        cap surt de neck_follow i el que falta fins a 1.0 se l queda el pit.
        Amb pes 0 no s afegeix el target, aixi no queden constraints amb un
        target que no fa res.
        """
        n = self.rig_name
        chest = (self.parent_joint
                 if self.parent_joint and cmds.objExists(self.parent_joint)
                 else None)
        if not chest:
            cmds.warning(f"[HorseNeck] No s ha trobat {self.parent_joint}: "
                         f"el coll no segueix l espina.")

        names = list(self.NECK_NAMES)
        for name, off, weight in zip(names, self.offsets, self.neck_follow):
            weight = max(0.0, min(1.0, float(weight)))
            targets = []
            if chest and weight < 1.0:
                targets.append((chest, 1.0 - weight))
            if self.head_ctrl and weight > 0.0:
                targets.append((self.head_ctrl, weight))
            if not targets:
                continue

            pac = cmds.parentConstraint([t for t, _ in targets], off, mo=True,
                                        n=f"{n}_{name}_follow_PAC")[0]
            aliases = cmds.parentConstraint(pac, q=True, weightAliasList=True)
            for alias, (_, w) in zip(aliases, targets):
                cmds.setAttr(f"{pac}.{alias}", w)

    def _aim_neck_to_head(self):
        """
        aimConstraint de cada control del coll al control del cap.

        L aim NO va al mateix node que el parentConstraint del cap: aquell va
        a l _OFF i aquest a l _SDK, un nivell mes avall. Si anessin tots dos
        al mateix transform es barallarien pel canal rotate i Maya nomes
        deixaria connectar el primer.

        Es crea amb maintainOffset, o sigui que al build no salta res: el que
        mante es la relacio que tenien ja posats, i a partir d aqui el coll
        apunta al cap tota l estona i s alinea sol. L animador encara pot
        girar el control a sobre, perque el CTRL penja de l SDK.

        Els dos controls del coll en porten. El tercer, que abans quedava
        fora perque el cap li queia just a sobre, ja no existeix.
        """
        if not self.head_ctrl:
            return []

        n = self.rig_name
        head_pos = cmds.xform(self.head_ctrl, q=True, ws=True, t=True)
        names = list(self.NECK_NAMES)
        self.aims = []

        for name, top, ctrl in zip(names, self.tops, self.controls):
            # el grup _SDK de la pila GRP > SPC > OFF > SDK > CTRL
            sdk = None
            node = top
            while node and node != ctrl:
                if node.split("|")[-1].upper().endswith("_SDK"):
                    sdk = node
                    break
                children = cmds.listRelatives(node, c=True, type="transform") or []
                node = children[0] if children else None

            if not sdk:
                cmds.warning(f"[HorseNeck] {ctrl} no te grup _SDK: sense ell "
                             f"l aim xocaria amb el parentConstraint de l _OFF. "
                             f"Aim de {name} no creat.")
                continue

            # Massa a prop del cap: l aim no tindria direccio on apuntar
            pos = cmds.xform(sdk, q=True, ws=True, t=True)
            if self._length(self._sub(head_pos, pos)) < 0.001:
                print(f"[HorseNeck] {name} esta damunt del cap: sense aim.")
                continue

            # El world up object es el GRUP D OFFSET del mateix control
            # (Character_neckBase_OFF, Character_neckMid_OFF): la referencia
            # de l up surt d ell mateix i no del cap, aixi que girar el cap
            # ja no li arrossega el roll. No hi ha cicle: l _OFF nomes depen
            # del seu parentConstraint, i l aim escriu a l _SDK, que en penja.
            up_object = self._offset_group(top, ctrl)

            aic = cmds.aimConstraint(
                self.head_ctrl, sdk, mo=True,
                aimVector=self.aim_vector,
                upVector=self.aim_up_vector,
                worldUpType="objectrotation",
                worldUpVector=self.aim_up_vector,
                worldUpObject=up_object,
                n=f"{n}_{name}_aim_AIC")[0]
            self.aims.append(aic)

        return self.aims

    # ------------------------------------------------------------------ #
    # 5. UVPIN (opcional)
    # ------------------------------------------------------------------ #
    def _build_pinned_joints(self, parent):
        n = self.rig_name
        shape = cmds.listRelatives(self.surface, s=True, f=True)[0]

        pin = cmds.createNode("uvPin", n=f"{n}_neckRibbon_UVP")
        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{pin}.deformedGeometry")
        cmds.setAttr(f"{pin}.normalizedIsoParms", 1)
        cmds.setAttr(f"{pin}.normalAxis", 1)    # Y = normal de la NURBS
        cmds.setAttr(f"{pin}.tangentAxis", 2)   # Z = tangent U (amplada)
        self.uv_pin = pin

        # Repartits uniformement DINS de la NURBS, sense tocar els extrems.
        # El repartiment compta tambe la RANURA DE LA TANGENT, que es la
        # ultima: amb 7 pins + la tangent surten 8 ranures i els pins van de
        # V 0.111 a V 0.778, un cada 0.111. Si es comptessin nomes els 7
        # pins, un cauria clavat a V 0.5, damunt del joint del mig.
        #
        # La formula (i+1)/(ranures+1) es la que els deixa per dins; amb
        # i/(n-1) el primer i l ultim anaven a les puntes.
        slots = self.pin_joints + (1 if self.tangent_jnt else 0)

        self.pinned = []
        for i in range(self.pin_joints):
            cmds.setAttr(f"{pin}.coordinate[{i}].coordinateU", 0.5)
            cmds.setAttr(f"{pin}.coordinate[{i}].coordinateV",
                         (i + 1) / float(slots + 1))

            cmds.select(clear=True)
            jnt = cmds.joint(n=f"{n}_neckPin_{i + 1:02d}_JNT")
            jnt = cmds.parent(jnt, parent)[0]
            for attr in ("translate", "rotate", "jointOrient"):
                cmds.setAttr(f"{jnt}.{attr}", 0, 0, 0)
            cmds.connectAttr(f"{pin}.outputMatrix[{i}]", f"{jnt}.offsetParentMatrix")
            self.pinned.append(jnt)
        cmds.select(clear=True)

        if len(self.pinned) > 1:
            self._fix_pin_axes()
        return self.pinned

    def _fix_pin_axes(self):
        """
        Assegura X al llarg del coll (cap al cap) i Y cap amunt.
        Segons el sentit en que ha quedat la NURBS, la normal o la tangent
        poden sortir girades: es comprova amb els dos primers joints.
        """
        pin = self.uv_pin
        _, y, _ = self._world_axes(self.pinned[0])
        if self._dot(y, (0, 1, 0)) < 0:
            cmds.setAttr(f"{pin}.normalAxis", 4)   # -Y

        x, _, p0 = self._world_axes(self.pinned[0])
        _, _, p1 = self._world_axes(self.pinned[1])
        if self._dot(x, self._sub(p1, p0)) < 0:
            current = cmds.getAttr(f"{pin}.tangentAxis")
            cmds.setAttr(f"{pin}.tangentAxis", 5 if current == 2 else 2)   # Z <-> -Z

    # ------------------------------------------------------------------ #
    def build(self):
        missing = [g for g in self.guides if not cmds.objExists(g)]
        if missing:
            cmds.error(f"[HorseNeck] Falten guies: {missing}")

        n = self.rig_name
        guide_pos = [cmds.xform(g, q=True, ws=True, t=True) for g in self.guides]

        # Sense cap no hi ha res que mani ni res que deformi la punta de la
        # NURBS: es torna a la cadena de sempre i el mig s hi fa carrec.
        if not self.head and self.head_world_space:
            cmds.warning("[HorseNeck] head=False: el coll torna a la cadena "
                         "neckBase > neckMid i la punta de la NURBS es queda "
                         "amb el joint de la base.")
            self.head_world_space = False

        # Sistemes i joints en espai de mon: no hereten transformacions
        module = cmds.createNode("transform", n=f"{n}_neck_GRP")
        sys_grp = cmds.createNode("transform", n=f"{n}_neckSystems_GRP", parent=module)
        jnt_grp = cmds.createNode("transform", n=f"{n}_neckJoints_GRP", parent=module)
        for grp in (sys_grp, jnt_grp):
            cmds.setAttr(f"{grp}.inheritsTransform", 0)
        cmds.setAttr(f"{sys_grp}.visibility", 0)
        ctrl_grp = cmds.createNode("transform", n=f"{n}_neckControls_GRP")

        self._build_surface(guide_pos, sys_grp)
        self._build_joints(guide_pos, jnt_grp)
        tops = self._build_controls(ctrl_grp)

        # El cap, ABANS del skin: el seu joint es una influencia mes de la
        # NURBS, i a mes els controls del coll el necessiten com a target.
        if self.head:
            head_parent = ctrl_grp if self.head_world_space else self.controls[-1]
            self._build_head(head_parent, jnt_grp)

        # La tangent del cap: joint normal amb control, abans del skin
        # perque tambe es una influencia de la NURBS.
        if self.head and self.tangent_joint:
            self._build_tangent_joint(jnt_grp)

        # Base + mig + cap + tangent deformen la NURBS
        self._skin_surface()

        if self.pin_joints:
            self._build_pinned_joints(jnt_grp)

        # --- Organitzacio -----------------------------------------------------
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(module, rig_grp)

        container = None
        if self.root_instance:
            container = (getattr(self.root_instance, "localCtl", None)
                         or getattr(self.root_instance, "body_ctl", None))
        if container and cmds.objExists(container):
            cmds.parent(ctrl_grp, container)

        # --- Qui segueix a qui ------------------------------------------------
        # Es fa amb els grups ja al seu lloc definitiu: el maintainOffset d un
        # parentConstraint congela la relacio del moment en que es crea.
        if self.head_world_space:
            # Blend pit/cap al grup d offset de cada control del coll
            self._link_neck_to_head()

            # ... i a mes el coll apunta al cap tota l estona
            if self.aim_at_head:
                self._aim_neck_to_head()
        elif self.parent_joint and cmds.objExists(self.parent_joint):
            # Muntatge antic: nomes la base segueix el pit, la cadena fa la resta
            cmds.parentConstraint(self.parent_joint, tops[0], mo=True,
                                  n=f"{n}_neckBase_follow_PAC")
        else:
            cmds.warning(f"[HorseNeck] No s ha trobat {self.parent_joint}: "
                         f"el coll no segueix l espina.")

        print(f"[HorseNeck] Ribbon construit: NURBS {self.u_spans}x{self.v_spans} spans "
              f"(grau {self.u_degree}/{self.v_degree}), "
              f"{len(self.joints) + (1 if self.head_joint else 0)} joints de skin, "
              f"{len(self.pinned)} pinned, {len(self.controls)} controls"
              f"{' + cap' if self.head_ctrl else ''}. "
              f"{'El cap mana i el coll el segueix ' + str(self.neck_follow) if self.head_world_space else 'Cadena FK classica'}.")
        return self