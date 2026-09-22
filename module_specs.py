# -*- coding: utf-8 -*-
"""
module_specs.py
===============

Vocabulario UNICO de modulos y features del autorig.

La UI y el build leen los dos de aqui. Si una feature no esta en esta tabla,
no existe: ni sale en la ventana ni se construye. Asi no puede pasar que la UI
mande "Soft IK" y el build compare con "soft" y no salte ningun error.

Cada feature tiene:
    key         -> nombre interno, el que viaja en la receta ("soft_ik")
    label       -> lo que ve el usuario en el arbol ("Soft IK")
    requires    -> otras features que necesita para funcionar
    default     -> si viene marcada al anadir el modulo
    implemented -> False si todavia no hay codigo detras (la UI la deshabilita
                   en vez de fingir que funciona)
"""


class Feature(object):

    __slots__ = ("key", "label", "requires", "default", "implemented")

    def __init__(self, key, label, requires=(), default=False, implemented=True):
        self.key = key
        self.label = label
        self.requires = tuple(requires)
        self.default = default
        self.implemented = implemented

    def __repr__(self):
        return "<Feature {}>".format(self.key)


# ---------------------------------------------------------------------------
# TABLA DE MODULOS
#
# order  -> orden OBLIGATORIO de construccion. No es el orden en que el usuario
#           pincha los botones: el chest tiene que existir antes que el brazo,
#           la pierna antes que los dedos del pie, etc.
# sides  -> lados posibles. "C" = centro, sin mirror.
# always -> features que van siempre. Se muestran marcadas y bloqueadas.
# optional -> lo que el usuario elige.
# ---------------------------------------------------------------------------
MODULE_SPECS = {

    "spine": {
        "label": "Spine",
        "order": 10,
        "sides": ["C"],
        "mirror_roots": [],
        "always": [
            Feature("fk", "FK"),
            Feature("ik_spline", "IK Spline"),
        ],
        "optional": [
            Feature("twist", "Twist"),
            Feature("ribbon", "Ribbon", implemented=False),
            Feature("stretch", "Stretch", implemented=False),
        ],
    },

    "arm": {
        "label": "Arm",
        "order": 20,
        "sides": ["L", "R"],
        # Raiz de la cadena de guias que hay que espejar para tener el lado R.
        # Solo la raiz: mirrorJoint ya se lleva toda la jerarquia de debajo.
        "mirror_roots": ["L_clavicule"],
        "always": [
            Feature("ik", "IK"),
            Feature("fk", "FK"),
            Feature("ikfk_switch", "IK/FK Switch"),
            Feature("pole_vector", "Pole Vector"),
        ],
        "optional": [
            Feature("curvature", "Curvature", default=True),
            # Twist NO depende de curvature: twist_module tiene fallback y se
            # crea su propia curva degree-2 si no le pasas source_curve.
            # Si curvature esta, se la pasamos y sale mejor.
            Feature("twist", "Twist", default=True),
            # default=True porque el autorig viejo montaba el soft IK en los
            # brazos siempre. Si lo dejas en False, el comportamiento por
            # defecto del rig cambia sin que nadie se entere.
            Feature("soft_ik", "Soft IK", default=True),
            # El pin SI depende del soft: necesita softTransform_node y
            # condition_node del diccionario que devuelve apply_soft_ik().
            Feature("pv_pin", "Pole Vector Pin", requires=("soft_ik",)),
            Feature("stretch", "Stretch", implemented=False),
        ],
    },

    "finger": {
        "label": "Finger",
        "order": 30,
        "sides": ["L", "R"],
        # Vacio a proposito: las guias de los dedos cuelgan de la muneca, asi
        # que ya vienen espejadas dentro de la jerarquia de L_clavicule.
        "mirror_roots": [],
        "always": [
            Feature("fk", "FK"),
        ],
        "optional": [
            # El IK de los dedos vive en fingersIk_module y es caro: cinco
            # ikHandles, cinco space switches y sus preferred angles. Por eso
            # se puede quitar aunque venga marcado por defecto.
            Feature("ik", "IK", default=True),
            # Los tres atributos de la mano son independientes: cada uno crea
            # su canal en el control de ajustes y sus set driven keys.
            Feature("fan", "Fan", default=True),
            Feature("spread", "Spread", default=True),
            Feature("fist", "Fist", default=True),
        ],
    },

    "leg": {
        "label": "Leg",
        "order": 40,
        "sides": ["L", "R"],
        "mirror_roots": ["L_hip"],
        "always": [
            Feature("ik", "IK"),
            Feature("fk", "FK"),
            Feature("ikfk_switch", "IK/FK Switch"),
            Feature("pole_vector", "Pole Vector"),
            # El reverse foot esta cosido dentro de LegModule/foot_module, no
            # se puede desactivar sin partir el modulo. Por eso va en always.
            Feature("reverse_foot", "Reverse Foot"),
        ],
        "optional": [
            Feature("curvature", "Curvature", default=True),
            Feature("twist", "Twist", default=True),
            Feature("soft_ik", "Soft IK", default=True),
            Feature("pv_pin", "Pole Vector Pin", requires=("soft_ik",)),
            Feature("toes", "Toes", default=True),
            Feature("stretch", "Stretch", implemented=False),
        ],
    },

    # -----------------------------------------------------------------------
    # CARA
    #
    # El orden entre ellos no es decorativo: la mandibula lee los controles de
    # comisura que crea la boca, asi que la boca va antes. Los cuatro tienen
    # que quedar entre las piernas (40) y el skinning (70).
    #
    # face=True: los usa mirror_module para poder saltarse la cara entera, y la
    # ventana para agruparlos en su propio panel.
    # -----------------------------------------------------------------------
    "mouth": {
        "label": "Mouth",
        "order": 50,
        "sides": ["L", "R"],
        "face": True,
        "mirror_roots": ["L_lip_end"],
        "always": [
            Feature("lip_curve", "Lip Curve"),
            Feature("muscle_surface", "Muscle Surface"),
        ],
        "optional": [],
    },

    "jaw": {
        "label": "Jaw",
        "order": 52,
        "sides": ["C"],
        "face": True,
        "mirror_roots": [],
        "always": [
            Feature("pinch_lines", "Pinch Lines"),
            Feature("lip_follow", "Lip Follow"),
        ],
        "optional": [],
    },

    "eyebrow": {
        "label": "Eyebrow",
        "order": 54,
        "sides": ["L", "R"],
        "face": True,
        # Las cejas son joints sueltos, no una jerarquia: hay que espejar los
        # diez uno a uno.
        "mirror_roots": ["L_eyebrow_root_{:02d}".format(i) for i in range(1, 11)],
        "always": [
            Feature("bezier_curve", "Bezier Curve"),
            Feature("motion_paths", "Motion Paths"),
        ],
        "optional": [],
    },

    "eye": {
        "label": "Eye",
        "order": 56,
        "sides": ["L", "R"],
        "face": True,
        # Las tres joints del ojo son independientes (el grupo las separo).
        "mirror_roots": ["L_eye_mid", "L_eye_mid_end", "L_eye_direct"],
        "always": [
            Feature("eyelid_lines", "Eyelid Lines"),
            Feature("aim", "Aim / Eye Direct"),
            Feature("in_between", "In-Between Controls"),
        ],
        "optional": [
            Feature("blink", "Blink", default=True),
            Feature("fleshy", "Fleshy Eye", default=True),
            # Los joints de loop se proyectan sobre las curvas Blinked, que son
            # el final de la cadena del blink. Sin blink no hay sobre que
            # proyectarlos.
            Feature("loop_joints", "Loop Joints", default=True,
                    requires=("blink",)),
        ],
    },

    "nose": {
        "label": "Nose",
        "order": 58,
        "sides": ["C"],
        "face": True,
        "mirror_roots": [],
        "always": [],
        "optional": [],
    },
}


#: Modulos de la cara. mirror_module los usa para poder saltarselos enteros.
FACE_MODULES = tuple(key for key, spec in MODULE_SPECS.items() if spec.get("face"))


# Modulos sin los que el rig no se sostiene. Si no estan en la receta se
# meten solos con un aviso: el chest cuelga de la espina, y la clavicula del
# brazo se constrainea al chest.
REQUIRED_MODULES = ("spine",)


# ---------------------------------------------------------------------------
# CONSULTAS (las usa la UI para pintar el arbol)
# ---------------------------------------------------------------------------
def module_types():
    """Tipos de modulo, ya en orden de construccion."""
    return sorted(MODULE_SPECS.keys(), key=lambda key: MODULE_SPECS[key]["order"])


def module_label(module_type):
    return MODULE_SPECS[module_type]["label"]


def module_sides(module_type):
    return list(MODULE_SPECS[module_type]["sides"])


def is_face(module_type):
    """True si el modulo es de cara (boca, mandibula, cejas, ojos, nas)."""
    return bool(MODULE_SPECS[module_type].get("face"))


def mirror_roots(module_type):
    """Guias raiz que hay que espejar para poder construir el lado R."""
    return list(MODULE_SPECS[module_type].get("mirror_roots", []))


def always_features(module_type):
    return list(MODULE_SPECS[module_type]["always"])


def optional_features(module_type):
    return list(MODULE_SPECS[module_type]["optional"])


def all_features(module_type):
    return always_features(module_type) + optional_features(module_type)


def find_feature(module_type, key):
    for feature in all_features(module_type):
        if feature.key == key:
            return feature
    return None


def default_feature_keys(module_type):
    """Features marcadas al anadir el modulo: las always y las default."""
    keys = {feature.key for feature in always_features(module_type)}
    keys |= {feature.key for feature in optional_features(module_type)
             if feature.default and feature.implemented}
    return keys


# ---------------------------------------------------------------------------
# RESOLUCION
# ---------------------------------------------------------------------------
def resolve_features(module_type, keys):
    """
    Deja el set de features listo para construir:
      - mete siempre las always
      - arrastra las dependencias que falten (pv_pin -> soft_ik)
      - tira las que no existen o no estan implementadas

    Returns:
        tuple: (set de keys, lista de avisos en texto)
    """
    warnings = []
    resolved = {feature.key for feature in always_features(module_type)}

    for key in set(keys or []):
        feature = find_feature(module_type, key)

        if feature is None:
            warnings.append("'{}' no es una feature de {}. Se ignora."
                            .format(key, module_type))
            continue

        if not feature.implemented:
            warnings.append("'{}' todavia no esta implementada en {}. Se ignora."
                            .format(feature.label, module_type))
            continue

        resolved.add(key)

    # Dependencias: se resuelven en bucle porque una dependencia puede traer
    # otra detras.
    changed = True
    while changed:
        changed = False
        for key in list(resolved):
            feature = find_feature(module_type, key)
            if feature is None:
                continue
            for needed in feature.requires:
                if needed not in resolved:
                    resolved.add(needed)
                    changed = True
                    needed_feature = find_feature(module_type, needed)
                    warnings.append(
                        "'{}' necesita '{}'. Se activa automaticamente.".format(
                            feature.label,
                            needed_feature.label if needed_feature else needed)
                    )

    return resolved, warnings


def normalize_recipe(recipe):
    """
    Deja la receta que viene de la UI lista para el build:
      - quita entradas duplicadas (mismo tipo + mismo lado)
      - resuelve features y dependencias de cada entrada
      - anade los modulos obligatorios que falten
      - ordena por el orden real de construccion

    Args:
        recipe (list): lista de dicts {"type": str, "side": str, "features": iterable}

    Returns:
        tuple: (receta normalizada, lista de avisos)
    """
    warnings = []
    normalized = []
    seen = set()

    for entry in recipe or []:
        module_type = entry.get("type")

        if module_type not in MODULE_SPECS:
            warnings.append("Modulo desconocido '{}'. Se ignora.".format(module_type))
            continue

        side = entry.get("side") or module_sides(module_type)[0]
        if side not in module_sides(module_type):
            warnings.append("El modulo {} no admite el lado '{}'. Se usa '{}'."
                            .format(module_type, side, module_sides(module_type)[0]))
            side = module_sides(module_type)[0]

        identity = (module_type, side)
        if identity in seen:
            warnings.append("{} {} esta duplicado en la lista. Se construye una vez."
                            .format(module_type, side))
            continue
        seen.add(identity)

        features, feature_warnings = resolve_features(module_type, entry.get("features"))
        warnings.extend("[{} {}] {}".format(module_type, side, text)
                        for text in feature_warnings)

        normalized.append({"type": module_type, "side": side, "features": features})

    # Modulos obligatorios que el usuario no ha anadido
    present_types = {entry["type"] for entry in normalized}
    for module_type in REQUIRED_MODULES:
        if module_type not in present_types:
            side = module_sides(module_type)[0]
            features, _ = resolve_features(module_type, default_feature_keys(module_type))
            normalized.append({"type": module_type, "side": side, "features": features})
            warnings.append(
                "El modulo '{}' es obligatorio y no estaba en la lista. Se anade."
                .format(module_type))

    normalized.sort(key=lambda entry: (MODULE_SPECS[entry["type"]]["order"],
                                       entry["side"]))
    return normalized, warnings


def describe_recipe(recipe):
    """Receta en texto, para imprimirla en el script editor antes de construir."""
    lines = []
    for entry in recipe:
        optional_keys = sorted(
            entry["features"] - {f.key for f in always_features(entry["type"])})
        labels = [find_feature(entry["type"], key).label for key in optional_keys]
        lines.append(" - {} {} [{}]".format(
            module_label(entry["type"]),
            entry["side"],
            ", ".join(labels) if labels else "solo lo basico"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MIXIN PARA LOS MODULOS DE RIG
# ---------------------------------------------------------------------------
class FeaturesMixin(object):
    """
    Lo heredan LimbModule, LegModule, SpineModule... Da un sitio unico donde
    preguntar si una feature esta activa.
    """

    def _init_features(self, module_type, features=None):
        self.module_type = module_type

        if features is None:
            # Nadie le ha pasado receta: se comporta como antes de todo esto,
            # con las features por defecto. Asi no rompemos los scripts viejos
            # que instancian el modulo a mano.
            features = default_feature_keys(module_type)

        self.features = set(features)

    def has(self, feature_key):
        return feature_key in getattr(self, "features", set())