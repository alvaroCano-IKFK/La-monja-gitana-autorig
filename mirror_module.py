import re

import maya.cmds as cmds

import module_specs


class Mirror(object):
    """
    Espeja las guias del lado L al lado R.

    Tres cosas cambian respecto a la version anterior:

    1. Es IDEMPOTENTE. Antes, darle al boton dos veces creaba R_clavicule1,
       R_clavicule2... porque mirrorJoint no comprueba si el destino ya existe.
       Ahora, si la guia R ya esta, se borra y se vuelve a espejar. Que es lo
       que uno espera del boton: mueves las guias de la izquierda, le das a
       Mirror y la derecha se actualiza.

    2. Lee la RECETA. Si en el arbol de la ventana solo hay un brazo L, no
       tiene sentido espejar la cadera. Solo se espeja lo que hace falta.

    3. Las cejas ya no pueden petar. En la version anterior, self.r_eyebrows se
       inicializaba dentro de un if pero el bucle que hacia append estaba
       fuera: si existia L_eyebrow_root_02 pero no L_eyebrow_root_01, saltaba
       un AttributeError. La indentacion estaba mal, no era intencionado.
    """

    # Las guias de la cara ya NO estan escritas aqui: boca, mandibula, cejas y
    # ojos son modulos de la receta, asi que sus mirror_roots viven en
    # module_specs igual que los del brazo y la pierna. Una sola tabla.

    def __init__(self, mirror_face=True):
        """
        Args:
            mirror_face (bool): False para saltarse boca, ojos y cejas. Util
                mientras se prueba solo el cuerpo.
        """
        self.mirror_face = mirror_face

        # Que se ha espejado en la ultima pasada, para poder consultarlo
        self.mirrored = []
        self.skipped = []
        self.replaced = []

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def mirror(self, recipe=None):
        """
        Espeja las guias.

        Args:
            recipe (list): la receta de la ventana. Si es None, o si viene
                vacia, se espeja todo (que es como se comportaba antes).
                Si trae modulos, solo se espejan las guias de los modulos
                que tengan una entrada del lado R.

        Returns:
            list: nombres de las guias raiz creadas en el lado R
        """
        self.mirrored = []
        self.skipped = []
        self.replaced = []

        roots = self._collect_roots(recipe)

        if not roots:
            cmds.warning("[Mirror] No hay ninguna guia que espejar.")
            return []

        for left_root in roots:
            self._mirror_one(left_root)

        self._report()

        return list(self.mirrored)

    # ------------------------------------------------------------------
    # QUE HAY QUE ESPEJAR
    # ------------------------------------------------------------------
    def _collect_roots(self, recipe):
        """
        Decide la lista de guias raiz a espejar a partir de la receta.

        Sin receta (o con el arbol vacio) se espeja todo: si no, darle a Mirror
        antes de configurar los modulos no haria nada y el usuario pensaria que
        el boton esta roto.
        """
        roots = []

        if not recipe:
            wanted = list(module_specs.module_types())
        else:
            # Solo los modulos que de verdad tienen un lado R en la receta.
            # Espejar la cadera para construir solo una pierna izquierda es
            # dejar guias sueltas en la escena que luego estorban.
            wanted = sorted({entry["type"] for entry in recipe
                             if entry.get("side") == "R"})

        for module_type in wanted:
            if not self.mirror_face and module_specs.is_face(module_type):
                continue
            roots.extend(module_specs.mirror_roots(module_type))

        # Sin duplicados y conservando el orden
        seen = set()
        unique = []
        for root in roots:
            if root not in seen:
                seen.add(root)
                unique.append(root)

        return unique

    # ------------------------------------------------------------------
    # ESPEJAR UNA GUIA
    # ------------------------------------------------------------------
    @staticmethod
    def right_name(left_name):
        """L_clavicule -> R_clavicule. Solo toca el prefijo, no el resto."""
        return re.sub(r"^L_", "R_", left_name)

    def _mirror_one(self, left_root):
        """
        Espeja una cadena de guias. Si el destino ya existe lo borra primero,
        para que el resultado sea el mismo le des al boton una vez o diez.
        """
        if not cmds.objExists(left_root):
            self.skipped.append(left_root)
            return None

        right_root = self.right_name(left_root)

        if cmds.objExists(right_root):
            # Se borra la jerarquia entera del lado R, no solo la raiz:
            # cmds.delete de un joint padre ya se lleva a los hijos.
            cmds.delete(right_root)
            self.replaced.append(right_root)

        result = cmds.mirrorJoint(left_root, myz=True, mb=True, sr=("L", "R"))

        if not result:
            cmds.warning("[Mirror] mirrorJoint no devolvio nada para "
                         "{}.".format(left_root))
            return None

        # mirrorJoint devuelve la lista de lo duplicado; el primero es la raiz
        created = result[0]

        # Si ya existia algo llamado R_loquesea en otro sitio de la escena,
        # Maya renombra a R_loquesea1 sin avisar. Mejor enterarse ahora que
        # cuando el build no encuentre la guia.
        if created != right_root:
            cmds.warning("[Mirror] Se esperaba '{}' pero Maya ha creado '{}'. "
                         "Revisa si hay nombres duplicados en la "
                         "escena.".format(right_root, created))

        self.mirrored.append(created)

        return created

    # ------------------------------------------------------------------
    def _report(self):
        if self.replaced:
            print("[Mirror] Reemplazadas {} guias que ya existian: {}".format(
                len(self.replaced), ", ".join(self.replaced)))

        if self.mirrored:
            print("[Mirror] Espejadas {} guias: {}".format(
                len(self.mirrored), ", ".join(self.mirrored)))

        if self.skipped:
            print("[Mirror] No estaban en la escena y se han saltado: "
                  "{}".format(", ".join(self.skipped)))