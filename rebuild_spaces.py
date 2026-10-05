"""
ESTO HA SIDO UNA PRUEBA, SE PODRÁ BORRAR EN CUALQUIER MOMENTO. NO ES PARTE DEL AUTORIG.
Relanza el space switching sobre el rig que ya esta en escena, sin rebuild.

ANTES DE EJECUTAR:

  - Todos los controles en pose de reposo (canales a cero). Los offsets se
    hornean con lo que haya en ese momento: si lo lanzas con el body girado,
    te quedas esa pose horneada dentro.
  - Si dejaste constraints en nodeState Blocked de alguna prueba anterior,
    devuelvelos a Normal: unblock_old_constraints() lo hace.

Pegalo en el Script Editor y ejecuta run().
"""

import importlib
import maya.cmds as cmds
import spaceSwitching_module

RIG = "Character"


def unblock_old_constraints():
    """Devuelve a Normal los parentConstraint de espacio que quedaran bloqueados."""
    cons = [c for c in cmds.ls(type="parentConstraint") if c.endswith("_SPC_PRC")]
    for con in cons:
        cmds.setAttr(f"{con}.nodeState", 0)
    if cons:
        print(f"[Spaces] {len(cons)} constraints viejos desbloqueados "
              "(el cleanup del modulo los borrara).")


def jobs_for(side):
    """Los mismos diccionarios que usa build_module._core_spaces."""
    return [
        (f"{side}_Arm_armIk_CTRL", {
            "MasterWalk": f"{RIG}_global_CTL",
            "Chest":      f"{RIG}_chestFix_CTL",
            "Body":       f"{RIG}_body_CTL",
            "Hip":        f"{RIG}_localHip_CTL",
            "Head":       f"{RIG}_head_CTRL",
        }),
        (f"{side}_Leg_legIk_CTRL", {
            "MasterWalk": f"{RIG}_global_CTL",
            "Body":       f"{RIG}_body_CTL",
            "Hip":        f"{RIG}_localHip_CTL",
        }),
        (f"{side}_Arm_poleVector_CTRL", {
            "MasterWalk": f"{RIG}_global_CTL",
            "Body":       f"{RIG}_body_CTL",
            "Chest":      f"{RIG}_chestFix_CTL",
            "ArmIk":      f"{side}_Arm_armIk_CTRL",
            "Clavicule":  f"{side}_Arm_clavicule_CTRL",
        }),
        (f"{side}_Leg_poleVector_CTRL", {
            "MasterWalk": f"{RIG}_global_CTL",
            "Body":       f"{RIG}_body_CTL",
            "LegIk":      f"{side}_Leg_legIk_CTRL",
        }),
        (f"{side}_Arm_shoulder_fk_CTRL", {
            "Clavicule": f"{side}_Arm_clavicule_CTRL",
            "Chest":     f"{RIG}_chestFix_CTL",
            "Body":      f"{RIG}_body_CTL",
        }),
        (f"{side}_Leg_thigh_fk_CTRL", {
            "MasterWalk": f"{RIG}_global_CTL",
            "Hip":        f"{RIG}_localHip_CTL",
            "Body":       f"{RIG}_body_CTL",
        }),
    ]


def run():
    importlib.reload(spaceSwitching_module)
    unblock_old_constraints()

    done = 0
    for side in ("L", "R"):
        for ctrl, spaces in jobs_for(side):
            if not cmds.objExists(ctrl):
                print(f"[Spaces] {ctrl} no existe, se salta.")
                continue
            spaceSwitching_module.SpaceModule(
                target_control=ctrl,
                space_dict=spaces,
                attr_name="Space_Switch",
                rig_name=RIG,
            ).build()
            done += 1

    print(f"\n[Spaces] {done} controles remontados. "
          "Prueba a rotar el masterWalk, el local y el body.")
