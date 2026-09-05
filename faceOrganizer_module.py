"""
faceOrganizer_module.py

Organizador de outliner comun para los modulos faciales (boca, mandibula,
ojos, cejas...). No construye rig: solo decide DONDE vive cada nodo.

    ----------------------------------------------------------------
    LA REGLA
    ----------------------------------------------------------------
    CONTROLES -> cuelgan del <rig>_local_CTL.
                 Los del lado R viven dentro de <rig>_mirrorBehaviour_GRP
                 (scaleX = -1), igual que los de body mechanics, para que
                 sus canales sean identicos a los de L y la animacion se
                 pueda copiar/pegar en espejo.

    SISTEMAS  -> joints, curvas, locators de uvPin, OFF/TRN, settings,
                 prebinds, trackers... NUNCA entran en un grupo con escala
                 negativa. Se quedan en local, con determinante positivo,
                 en su propia rama.
    ----------------------------------------------------------------

Estructura resultante:

    C_<rig>_face_GRP                      (raiz de sistemas faciales)
        |- C_<rig>_faceSystems_GRP
             |- C_<rig>_mouthSystems_GRP
             |     |- C_<rig>_mouthJoints_GRP
             |     |- C_<rig>_mouthCurves_GRP
             |     |- C_<rig>_mouthLocators_GRP
             |     |     |- C_<rig>_mouthProjected_GRP   (inheritsTransform off)
             |     |     |- C_<rig>_mouthTrackers_GRP    (inheritsTransform off)
             |     |- C_<rig>_mouthSetup_GRP
             |- C_<rig>_jawSystems_GRP
                   |- ...

    <rig>_local_CTL
        |- C_<rig>_faceControls_GRP       (centro y lado L)
        |     |- C_<rig>_mouthControls_GRP
        |     |     |- C_<rig>_mouthCenterControls_GRP
        |     |     |- L_<rig>_mouthControls_GRP
        |     |- C_<rig>_jawControls_GRP
        |- <rig>_mirrorBehaviour_GRP      (scaleX = -1, ya existe en RigRoot)
              |- R_<rig>_faceControls_GRP
                    |- R_<rig>_mouthControls_GRP

Todos los grupos de organizacion se crean en identidad y no se mueven
nunca, asi que colgar cosas de ellos no cambia ni una sola matriz mundial.
La unica excepcion consciente es la rama R de controles, que hereda el
scaleX = -1 del mirrorBehaviour: ahi el reparenting SI es funcional y por
eso pasa por mirror_control_group(), que limpia la compensacion que Maya
escribe al reparentar.
"""

import maya.cmds as cmds


class FaceOrganizer(object):

    def __init__(self, rig_name="Character", root_instance=None,
                 parent_systems_to_rig=False, controls_parent=None):
        """
        controls_parent:
            Nodo del que cuelgan las dos ramas de controles faciales. Si es
            None se usa el <rig>_local_CTL. Cuando la cara tenga que seguir a
            la cabeza, pasa aqui el control/joint de cabeza: las dos ramas
            (normal y espejo) se mueven juntas y la simetria se mantiene.

        parent_systems_to_rig:
            False (por defecto) -> C_<rig>_face_GRP se queda en la raiz del
            mundo, exactamente como estaba antes. Cero riesgo.

            True -> se mete bajo <rig>_rig_GRP. Ojo: ese grupo esta
            scaleConstrained al globalCtl, asi que los nodos que reciben una
            matriz de MUNDO por offsetParentMatrix (los locators del uvPin)
            se transformarian dos veces al escalar el rig. Por eso los
            subgrupos que los contienen se marcan con inheritsTransform = 0
            (ver ensure_group(..., world_driven=True)).
        """
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.parent_systems_to_rig = parent_systems_to_rig
        self.controls_parent = controls_parent
        self.center = f"C_{rig_name}"

    # ------------------------------------------------------------------
    # NODOS DEL RIG ROOT
    # ------------------------------------------------------------------
    def _rig_grp(self):
        name = f"{self.rig_name}_rig_GRP"
        if self.root_instance is not None and hasattr(self.root_instance, "get_rig_grp"):
            name = self.root_instance.get_rig_grp()
        return name if cmds.objExists(name) else None

    def _local_ctl(self):
        name = f"{self.rig_name}_local_CTL"
        if self.root_instance is not None:
            name = getattr(self.root_instance, "localCtl", None) or name
        return name if cmds.objExists(name) else None

    # ------------------------------------------------------------------
    # CREACION DE GRUPOS
    # ------------------------------------------------------------------
    def ensure_group(self, group_name, parent_group=None, world_driven=False):
        """
        Devuelve `group_name`, creandolo vacio en la raiz del mundo si no
        existe. Idempotente.

        world_driven=True marca el grupo con inheritsTransform = 0: para
        grupos que contienen nodos que ya reciben una matriz de mundo
        (offsetParentMatrix del uvPin, motionPath, constraints). Asi da
        igual donde acabe colgado el grupo, sus hijos no se transforman
        dos veces.
        """
        group_node = self.resolve(group_name, parent_group)
        if group_node is None:
            group_node = cmds.group(em=True, world=True, n=group_name)
            group_node = (cmds.ls(group_node, long=True) or [group_node])[0]

        if parent_group:
            parent_node = self.resolve(parent_group)
            if parent_node:
                current_parent = cmds.listRelatives(group_node, parent=True,
                                                    fullPath=True) or []
                if not current_parent or current_parent[0] != parent_node:
                    group_node = cmds.parent(group_node, parent_node, relative=True)[0]
                    group_node = (cmds.ls(group_node, long=True) or [group_node])[0]

        if world_driven:
            try:
                if cmds.getAttr(f"{group_node}.inheritsTransform"):
                    cmds.setAttr(f"{group_node}.inheritsTransform", 0)
            except Exception:
                pass

        return group_node

    # ------------------------------------------------------------------
    # NOMBRES DUPLICADOS
    # ------------------------------------------------------------------
    def resolve(self, name, preferred_parent=None):
        """
        Devuelve el path largo de `name`, o None si no existe.

        Maya permite dos nodos con el mismo nombre corto si cuelgan de
        padres distintos, y a partir de ahi cualquier cmds sobre el nombre
        corto revienta con "More than one object matches name". Pasa, por
        ejemplo, cuando build() crea <lado>_<rig>_mouthControls_GRP en la
        raiz mientras el organizador ya habia creado uno dentro de la rama
        de controles.

        Si hay varios, se quedan todos fusionados en uno: gana el que cuelga
        de `preferred_parent` (o el que tenga mas hijos), los hijos de los
        demas se mueven dentro conservando sus valores locales y los
        duplicados vacios se borran.
        """
        if not name:
            return None
        matches = cmds.ls(name, long=True) or []
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        parent_path = None
        if preferred_parent:
            parent_matches = cmds.ls(preferred_parent, long=True) or []
            parent_path = parent_matches[0] if parent_matches else None

        def score(path):
            under_parent = bool(parent_path and path.startswith(parent_path + "|"))
            children = len(cmds.listRelatives(path, children=True, fullPath=True) or [])
            return (under_parent, children)

        matches.sort(key=score, reverse=True)
        keeper, duplicates = matches[0], matches[1:]

        cmds.warning(f"[FaceOrganizer] '{name}' estaba duplicado "
                     f"({len(matches)} nodos). Fusionando en {keeper}.")

        for duplicate in duplicates:
            children = cmds.listRelatives(duplicate, children=True, fullPath=True) or []
            for child in children:
                try:
                    cmds.parent(child, keeper, relative=True)
                except Exception as error:
                    cmds.warning(f"[FaceOrganizer] No se pudo mover '{child}' "
                                 f"a '{keeper}': {error}")
            if not (cmds.listRelatives(duplicate, children=True) or []):
                try:
                    cmds.delete(duplicate)
                except Exception:
                    pass

        return (cmds.ls(name, long=True) or [keeper])[0]

    # ------------------------------------------------------------------
    # RAICES
    # ------------------------------------------------------------------
    def face_root(self):
        """C_<rig>_face_GRP: raiz de TODO lo facial que no es un control."""
        root_grp = self.ensure_group(f"{self.center}_face_GRP")
        if self.parent_systems_to_rig:
            rig_grp = self._rig_grp()
            if rig_grp:
                current = cmds.listRelatives(root_grp, parent=True) or []
                if not current or current[0] != rig_grp:
                    cmds.parent(root_grp, rig_grp, relative=True)
        return root_grp

    def systems_root(self):
        """C_<rig>_faceSystems_GRP: todo en local, sin escalas negativas."""
        return self.ensure_group(f"{self.center}_faceSystems_GRP", self.face_root())

    def _controls_parent(self):
        """
        De donde cuelgan las dos ramas de controles de la cara (la normal y
        la de espejo). Por defecto el local_CTL; pasa `controls_parent` en el
        constructor para colgarlas del control de cabeza cuando exista.
        """
        if self.controls_parent and cmds.objExists(self.controls_parent):
            return self.controls_parent
        return self._local_ctl() or self.face_root()

    def controls_root(self):
        """C_<rig>_faceControls_GRP: controles de centro y de lado L."""
        return self.ensure_group(f"{self.center}_faceControls_GRP",
                                 self._controls_parent())

    def mirror_root(self):
        """
        C_<rig>_faceMirrorBehaviour_GRP: grupo con scaleX = -1 donde vive la
        rama R de controles.

        Es propio de la cara y NO el <rig>_mirrorBehaviour_GRP global a
        proposito. El global cuelga del local_CTL y lo comparte todo el body
        mechanics, asi que la cara no podria seguir a la cabeza sin
        arrastrarse el resto del rig. Con uno propio, la rama de espejo y la
        rama normal cuelgan siempre del mismo sitio (controls_parent), asi
        que basta con mover/constreñir ese padre al control de cabeza el dia
        que se enganche la cara.
        """
        mirror_grp = f"{self.center}_faceMirrorBehaviour_GRP"
        created = not cmds.objExists(mirror_grp)
        mirror_grp = self.ensure_group(mirror_grp, self._controls_parent())
        if created or cmds.getAttr(f"{mirror_grp}.scaleX") > 0:
            cmds.setAttr(f"{mirror_grp}.scaleX", -1)
        return mirror_grp

    def mirror_controls_root(self):
        """R_<rig>_faceControls_GRP, dentro del grupo de escala negativa."""
        return self.ensure_group(f"R_{self.rig_name}_faceControls_GRP",
                                 self.mirror_root())

    # ------------------------------------------------------------------
    # RAICES POR MODULO
    # ------------------------------------------------------------------
    def module_systems_root(self, module_name):
        """C_<rig>_<module>Systems_GRP."""
        return self.ensure_group(f"{self.center}_{module_name}Systems_GRP",
                                 self.systems_root())

    def module_controls_root(self, module_name):
        """
        C_<rig>_<module>Controls_GRP: contenedor del centro y del lado L.
        Se queda FUERA del mirror.
        """
        return self.ensure_group(f"{self.center}_{module_name}Controls_GRP",
                                 self.controls_root())

    def side_controls_group(self, module_name, side):
        """
        Grupo de controles de un lado concreto.

          C / L -> dentro de C_<rig>_<module>Controls_GRP
          R     -> dentro de R_<rig>_faceControls_GRP (escala negativa)
        """
        if side == "R":
            parent = self.mirror_controls_root()
        else:
            parent = self.module_controls_root(module_name)
        return self.ensure_group(f"{side}_{self.rig_name}_{module_name}Controls_GRP",
                                 parent)

    # ------------------------------------------------------------------
    # MOVER NODOS
    # ------------------------------------------------------------------
    def park(self, node_name, destination_group):
        """
        Mete `node_name` en `destination_group` SOLO si esta colgando de la
        raiz del mundo. Si ya tiene padre no se toca: esa jerarquia es
        funcional y no es asunto del organizador.

        Parent RELATIVO a proposito: el grupo destino esta en identidad, asi
        que conservar los valores locales conserva la matriz mundial exacta
        (skinClusters, uvPin, offsetParentMatrix y constraints siguen dando
        lo mismo) y Maya no intenta escribir en canales conectados.
        """
        if not node_name:
            return False
        node_name = self.resolve(node_name)
        destination_group = self.resolve(destination_group)
        if not node_name or not destination_group:
            return False
        if cmds.listRelatives(node_name, parent=True):
            return False

        try:
            cmds.parent(node_name, destination_group, relative=True)
        except Exception as error:
            cmds.warning(f"[FaceOrganizer] No se pudo ordenar '{node_name}' "
                         f"dentro de '{destination_group}': {error}")
            return False
        return True

    def move(self, node_name, destination_group, preserve_world=True):
        """
        Como park() pero a la fuerza: mueve el nodo aunque ya tenga padre.
        Se usa para recolocar los controles que build() dejo colgando
        directamente del mirrorBehaviour_GRP.

        preserve_world=True conserva la matriz mundial (Maya recalcula los
        canales locales). Entre dos grupos que estan en la misma pose eso
        deja los valores locales igual que estaban.
        """
        if not node_name:
            return False
        node_name = self.resolve(node_name)
        destination_group = self.resolve(destination_group)
        if not node_name or not destination_group:
            return False

        current = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
        if current and current[0] == destination_group:
            return True

        try:
            cmds.parent(node_name, destination_group, relative=not preserve_world)
        except Exception as error:
            cmds.warning(f"[FaceOrganizer] No se pudo mover '{node_name}' a "
                         f"'{destination_group}': {error}")
            return False
        return True

    # ------------------------------------------------------------------
    # MIRROR DE CONTROLES
    # ------------------------------------------------------------------
    def counterpart(self, node_name, from_side="R", to_side="L"):
        """R_<rig>_levator_GRP -> L_<rig>_levator_GRP."""
        if not node_name:
            return None
        short_name = node_name.split("|")[-1]
        prefix = f"{from_side}_{self.rig_name}_"
        if not short_name.startswith(prefix):
            return None
        return f"{to_side}_{self.rig_name}_" + short_name[len(prefix):]

    def _set_trs_from(self, node, source):
        """Copia translate / rotate / scale locales de `source` a `node`."""
        for attr in ("translate", "rotate", "scale"):
            for axis in "XYZ":
                plug = f"{node}.{attr}{axis}"
                try:
                    if cmds.getAttr(plug, lock=True) or cmds.listConnections(
                            plug, source=True, destination=False, plugs=True):
                        continue
                    cmds.setAttr(plug, cmds.getAttr(f"{source}.{attr}{axis}"))
                except Exception:
                    continue

    def mirror_control_group(self, group_name, destination=None,
                             copy_from_counterpart=True):
        """
        Mete un grupo raiz de control del lado R dentro de la rama de escala
        negativa y deja sus canales locales limpios.

        Al reparentar conservando el mundo, Maya compensa el scaleX = -1 del
        padre escribiendo un scale negativo (o un flip de 180) en el hijo:
        eso anula el mirror. Por eso, despues de mover, se copian los valores
        locales del grupo homologo del lado L. Si el rig es simetrico el
        resultado es el mismo sitio de siempre, pero ahora con
        comportamiento de espejo: el canal tx del control R hace lo contrario
        que el del control L, y la animacion se puede pegar en espejo.

        Es el mismo truco que ya hacia build() a mano con end_lip_GRP.

        Devuelve el grupo, o None si no se pudo hacer.
        """
        if not group_name:
            return None
        group_name = self.resolve(group_name)
        if not group_name:
            return None

        destination = destination or self.mirror_controls_root()
        if not self.move(group_name, destination, preserve_world=True):
            return None

        # El path largo cambia al mover: hay que volver a resolverlo.
        group_name = self.resolve(group_name.split("|")[-1]) or group_name

        if copy_from_counterpart:
            twin = self.resolve(self.counterpart(group_name) or "")
            if twin:
                self._set_trs_from(group_name, twin)
            else:
                cmds.warning(f"[FaceOrganizer] '{group_name}' no tiene homologo "
                             f"en L; se deja la compensacion de Maya. Revisa "
                             f"sus canales a mano.")
        return group_name

    # ------------------------------------------------------------------
    # COMPENSACION EN EL LADO DEL SISTEMA
    # ------------------------------------------------------------------
    def mirror_local_off(self, node_name, group_name=None):
        """
        Envuelve un _Local_OFF del lado R en un grupo con scaleX = -1.

        ESTO es lo que produce el espejo de verdad. El sistema lee la matriz
        LOCAL del control (ctrl.matrix) y la reaplica sobre este OFF, asi que
        mover el grupo del control a una rama con escala negativa NO cambia
        nada del deformador: el espejo tiene que ocurrir tambien aqui, en el
        lado del sistema. Es exactamente lo que ya hacia a mano
        R_<rig>_mouthLocalMirror_GRP con la comisura.

        Orden importante:
          1. se crea el grupo en el mismo padre y en la misma pose que el OFF
          2. se mete el OFF dentro conservando mundo (queda en identidad)
          3. SOLO ENTONCES se pone scaleX = -1
        Asi el OFF no recibe ninguna compensacion negativa en sus canales:
        se queda en el mismo sitio, con el eje X volteado.

        Si el OFF esta gobernado por un parentConstraint, se rehace despues
        del volteo (borrar -> envolver -> volver a constreñir con mo=True),
        porque el offset de mo=True se calculo antes y ya no vale.

        Idempotente: si ya cuelga de un grupo con scaleX negativo, no hace
        nada.
        """
        if not node_name:
            return None
        node_name = self.resolve(node_name)
        if not node_name:
            return None

        parent = (cmds.listRelatives(node_name, parent=True, fullPath=True) or [None])[0]
        if parent and cmds.getAttr(f"{parent}.scaleX") < 0:
            return parent

        # 0. Constraint previo: apuntar los drivers y borrarlo.
        constraints = cmds.listRelatives(node_name, type="parentConstraint") or []
        drivers = []
        for constraint in constraints:
            drivers.extend(cmds.parentConstraint(constraint, q=True, tl=True) or [])
        if constraints:
            cmds.delete(constraints)

        # 1-2-3. Envolver.
        short_name = node_name.split("|")[-1]
        group_name = group_name or f"{short_name}_localMirror_GRP"
        mirror_grp = self.resolve(group_name)
        if mirror_grp is None:
            mirror_grp = cmds.group(em=True, world=True, n=group_name)
            if parent:
                mirror_grp = cmds.parent(mirror_grp, parent, relative=False)[0]
            cmds.matchTransform(mirror_grp, node_name)
            node_name = cmds.parent(node_name, mirror_grp, relative=False)[0]
        mirror_grp = (cmds.ls(mirror_grp, long=True) or [mirror_grp])[0]
        cmds.setAttr(f"{mirror_grp}.scaleX", -1)

        # 4. Rehacer el constraint con el offset nuevo.
        for driver in drivers:
            if cmds.objExists(driver):
                cmds.parentConstraint(driver, node_name, mo=True)

        return mirror_grp