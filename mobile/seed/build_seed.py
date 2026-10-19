"""Genera mobile/src/seed-foods.js a partir de USDA FoodData Central (SR Legacy, dominio público).

Cada alimento se eligió a mano (nombre en español -> fdc_id) y lleva el id de USDA para poder verificarlo.
Los pesos de porción salen de la tabla food_portion de USDA.

Uso:  python3 -I mobile/seed/build_seed.py <carpeta con food.csv y food_nutrient.csv de SR Legacy>
Datos: https://fdc.nal.usda.gov/download-datasets  (FoodData_Central_sr_legacy_food_csv_2018-04.zip)
"""
import csv, json, sys
from pathlib import Path

# (nombre en español, fdc_id, gramos de porción | None, descripción de la porción | None)
CURATED = [
 # Cereales y tubérculos
 ("Tortilla de maíz", 175036, 24, "1 tortilla"), ("Tortilla de harina", 167535, 49, "1 tortilla"),
 ("Arroz blanco cocido", 168878, 158, "1 taza"), ("Arroz integral cocido", 169704, None, None),
 ("Avena en hojuelas (cruda)", 173904, 27, "⅓ de taza"), ("Avena cocida con agua", 173905, None, None),
 ("Pan blanco de caja", 174924, 29, "1 rebanada"), ("Pan integral de caja", 172688, 32, "1 rebanada"),
 ("Pan duro tipo bolillo (aprox.)", 175031, 57, "1 pieza"), ("Pasta cocida", 169737, 124, "1 taza de espagueti"),
 ("Papa cocida con cáscara", 170438, 136, "1 papa"), ("Camote horneado", 168483, 60, "1 chico"),
 ("Elote cocido (granos)", 169999, 103, "1 elote mediano"), ("Totopos de maíz blanco, salados", 167558, 28, "1 onza"),
 ("Concha de taco horneada", 172800, None, None), ("Galletas saladas", 172746, None, None),
 # Leguminosas
 ("Frijol negro cocido (sin sal)", 173735, 172, "1 taza"), ("Frijol pinto cocido (sin sal)", 175200, None, None),
 ("Frijoles refritos enlatados", 172438, None, None), ("Lentejas cocidas (sin sal)", 172421, 198, "1 taza"),
 ("Garbanzo cocido (sin sal)", 173757, None, None),
 # Proteínas
 ("Pechuga de pollo asada, sin piel", 171477, 86, "½ pechuga"), ("Muslo de pollo asado, sin piel", 172388, None, None),
 ("Huevo entero cocido", 173424, 50, "1 huevo grande"), ("Huevo entero crudo", 171287, None, None), ("Clara de huevo cruda", 172183, None, None),
 ("Carne molida de res 85/15, a la plancha", 174032, 77, "1 hamburguesa (¼ lb crudo)"), ("Bistec de res (round), cocido", 170638, None, None),
 ("Lomo de cerdo asado", 167821, None, None), ("Atún en agua, escurrido", 173709, 165, "1 lata"),
 ("Tilapia cocida", 175177, None, None), ("Camarón cocido", 175180, 85, "85 g (3 oz)"), ("Salmón del Atlántico cocido", 175168, None, None),
 ("Sardina en salsa de tomate", 175140, None, None), ("Chorizo de cerdo (crudo)", 173859, None, None),
 # Lácteos
 ("Leche entera", 171265, 244, "1 taza"), ("Leche semidescremada (2 %)", 171267, None, None), ("Leche descremada", 171269, None, None),
 ("Yogur natural entero", 171284, 170, "1 envase"), ("Yogur griego natural entero", 171304, None, None), ("Yogur natural bajo en grasa", 170886, None, None),
 ("Queso fresco", 172223, 122, "1 taza desmenuzado"), ("Queso cotija", 170898, None, None), ("Queso añejo", 172201, None, None),
 ("Queso Monterrey", 170844, None, None), ("Queso cottage", 172179, None, None), ("Mezcla de quesos estilo mexicano", 171288, None, None),
 ("Crema ácida", 171257, 12, "1 cucharada"), ("Crema para batir", 170859, None, None), ("Mantequilla con sal", 173410, 14, "1 cucharada"),
 # Grasas, frutos secos y dulces
 ("Aceite de oliva", 171413, 13.5, "1 cucharada"), ("Aceite de maíz", 171029, None, None), ("Aguacate", 171705, 50, "⅓ de aguacate"),
 ("Almendras", 170567, 28, "1 onza"), ("Nueces", 170187, None, None), ("Cacahuate crudo", 172430, 28, "1 onza"),
 ("Crema de cacahuate", 174266, 32, "2 cucharadas"), ("Semillas de chía", 170554, None, None), ("Chocolate amargo (70–85 % cacao)", 170273, None, None),
 ("Miel de abeja", 169640, 21, "1 cucharada"), ("Azúcar", 169655, 4.2, "1 cucharadita"),
 # Frutas
 ("Manzana con cáscara", 171688, 182, "1 mediana"), ("Plátano", 173944, 118, "1 mediano"), ("Naranja", 169097, 131, "1 fruta"),
 ("Mango", 169910, 165, "1 taza picado"), ("Papaya", 169926, None, None), ("Sandía", 167765, None, None), ("Melón", 169092, None, None),
 ("Fresa", 167762, None, None), ("Uva", 174683, None, None), ("Piña", 169124, None, None), ("Limón (lima ácida)", 168155, None, None),
 ("Guayaba", 173044, None, None), ("Pera", 169118, None, None), ("Durazno", 169928, None, None), ("Jugo de naranja natural", 169098, None, None),
 # Verduras
 ("Jitomate", 170457, 123, "1 mediano"), ("Cebolla", 170000, 110, "1 mediana"), ("Chile jalapeño", 168576, 14, "1 chile"),
 ("Chile serrano", 169395, None, None), ("Nopal crudo", 168571, 86, "1 taza rebanado"), ("Nopal cocido (sin sal)", 169388, None, None),
 ("Calabacita", 169291, None, None), ("Zanahoria", 170393, None, None), ("Lechuga romana", 169247, None, None), ("Pepino con cáscara", 168409, None, None),
 ("Espinaca cruda", 168462, None, None), ("Brócoli crudo", 170379, None, None), ("Chayote crudo", 170402, None, None), ("Cilantro", 169997, None, None),
 ("Ajo", 169230, None, None), ("Champiñón", 169251, None, None), ("Pimiento morrón rojo", 170108, None, None), ("Tomate verde", 168566, None, None),
 # Bebidas y salsas
 ("Refresco de cola", 174852, 370, "1 lata de 355 ml"), ("Café negro", 171890, None, None), ("Salsa roja lista para servir", 174524, None, None),
]

def main(d):
    d = Path(d)
    desc = {r["fdc_id"]: r["description"] for r in csv.DictReader(open(d / "food.csv", encoding="utf-8"))}
    nut = {}
    for r in csv.DictReader(open(d / "food_nutrient.csv", encoding="utf-8")):
        if r["nutrient_id"] in ("1003", "1004", "1005", "1008"): nut.setdefault(r["fdc_id"], {})[r["nutrient_id"]] = float(r["amount"])
    out, bad = [], []
    for name, fid, sg, sl in CURATED:
        m = nut[str(fid)]; kcal, p, c, f = m["1008"], m["1003"], m["1005"], m["1004"]
        exp = 4 * p + 4 * c + 9 * f
        if abs(kcal - exp) > max(0.15 * max(kcal, exp), 20): bad.append((name, fid, kcal, round(exp)))
        out.append({"id": f"usda-{fid}", "name": name, "kcal": round(kcal, 1), "p": round(p, 1), "c": round(c, 1), "f": round(f, 1),
                    "servingG": sg, "servingLabel": sl, "fdc": fid, "usda": desc[str(fid)][:90]})
    ids = [o["id"] for o in out]; assert len(ids) == len(set(ids)), "ids duplicados"
    here = Path(__file__).resolve().parent.parent / "src" / "seed-foods.js"
    here.write_text("/* Generado por mobile/seed/build_seed.py. Fuente: USDA FoodData Central, SR Legacy (dominio público). */\n"
                    "const SEED_FOODS = " + json.dumps(out, ensure_ascii=False, indent=0) + ";\n", encoding="utf-8")
    print(f"{len(out)} alimentos -> {here.name}")
    print("kcal declaradas que no cuadran con 4P+4C+9G (revisar):", bad or "ninguno")

main(sys.argv[1])
