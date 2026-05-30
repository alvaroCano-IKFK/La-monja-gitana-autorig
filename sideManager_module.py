"""
side_manager.py
---------------
Centraliza toda la lógica de lado (L / R) del autorig.

Uso básico:
    sm = SideManager("L")
    sm = SideManager("R")

El resto de módulos importan SideManager y le preguntan lo que necesiten.
"""


class SideManager(object):

    VALID_SIDES = ("L", "R")

    def __init__(self, side):
        side = side.upper()
        if side not in self.VALID_SIDES:
            raise ValueError(f"Side '{side}' no válido. Usa 'L' o 'R'.")
        self.side = side

    # ------------------------------------------------------------------
    # Helpers de nomenclatura
    # ------------------------------------------------------------------

    def prefix(self, name):
        """Devuelve el nombre con el prefijo de lado: 'L_shoulder'."""
        return f"{self.side}_{name}"

    def prefix_list(self, names):
        """Aplica prefix() a una lista de nombres."""
        return [self.prefix(n) for n in names]

    # ------------------------------------------------------------------
    # Orientación de joints
    # ------------------------------------------------------------------

    @property
    def joint_orient(self):
        """Eje primario de orientación (igual para ambos lados)."""
        return "xyz"

    @property
    def secondary_orient(self):
        """
        Eje secundario.
        L → yup   (codo/rodilla apunta hacia arriba / hacia atrás)
        R → ydown (mirror especular)
        """
        return "yup" if self.side == "L" else "ydown"

    @property
    def is_right(self):
        return self.side == "R"

    @property
    def is_left(self):
        return self.side == "L"

    # ------------------------------------------------------------------
    # Posiciones en mirror
    # ------------------------------------------------------------------

    def mirror_pos(self, pos):
        """
        Devuelve la posición reflejada en X para el lado R.
        Si el lado es L devuelve la posición sin tocar.

        Acepta tupla/lista de 3 floats: (x, y, z)
        """
        if self.is_right:
            return (-pos[0], pos[1], pos[2])
        return tuple(pos)

    def mirror_pos_list(self, positions):
        """Aplica mirror_pos() a una lista de posiciones."""
        return [self.mirror_pos(p) for p in positions]

    # ------------------------------------------------------------------
    # repr útil para debug
    # ------------------------------------------------------------------

    def __repr__(self):
        return (
            f"SideManager(side='{self.side}', "
            f"secondary_orient='{self.secondary_orient}')"
        )