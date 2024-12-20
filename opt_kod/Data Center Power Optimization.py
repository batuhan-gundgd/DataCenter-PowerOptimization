import gurobipy as gp
from gurobipy import GRB
import numpy as np
import matplotlib.pyplot as plt

# Parametreler
T = 24  # Zaman dilimi: 24 saat

# PV enerjisi (kW)
P_PV = [0, 0, 0 , 20, 110, 240, 350, 460, 550, 640, 730, 720, 710, 690, 90, 80, 70, 60, 50, 40, 30, 20, 10, 0]

# Talep (kW)
P_demand = [190, 185, 180, 195, 310, 420, 440, 550, 580, 640, 630, 530, 515, 410, 400, 390, 380, 345, 370, 365, 320, 355, 250, 245]

# Spot fiyatlar (USD/kWh)
C_grid = [0.1, 0.12, 0.11, 0.13, 0.15, 0.18, 0.2, 0.22, 0.23, 0.24, 0.22, 0.2, 0.18, 0.17, 0.16, 0.14, 0.13, 0.12, 0.11, 0.1, 0.1, 0.12, 0.13, 0.15]

# Hidrojen bataryası parametreleri
SOC_H2_max = 1000  # Maksimum kapasite (kWh)
SOC_H2_min = 100   # Minimum kapasite (kWh)
SOC_H2_0 = SOC_H2_min  # Başlangıç seviyesi

# ESD parametreleri
SOC_ESD_max = 500  # ESD Maksimum kapasite (kWh)
SOC_ESD_min = 50   # ESD Minimum kapasite (kWh)
SOC_ESD_0 = SOC_ESD_min  # Başlangıç seviyesi

# Verimlilikler
eta_electrolyzer = 0.8  # Elektrolizör verimliliği
eta_fuel_cell = 0.7     # Yakıt hücresi verimliliği

# Eşik fiyat (threshold price)
threshold_price = 0.18  # USD/kWh

# Model başlat
model = gp.Model("HydrogenBatteryOptimization")

# Değişkenler
P_grid = model.addVars(T, vtype=GRB.CONTINUOUS, name="P_grid")              # Şebekeden enerji alımı
P_sell = model.addVars(T, vtype=GRB.CONTINUOUS, name="P_sell")              # Şebekeye satış
P_electrolyzer = model.addVars(T, vtype=GRB.CONTINUOUS, name="P_electrolyzer")  # Elektrolizör gücü
P_fuel_cell = model.addVars(T, vtype=GRB.CONTINUOUS, name="P_fuel_cell")        # Yakıt hücresi gücü
SOC_H2 = model.addVars(T, vtype=GRB.CONTINUOUS, name="SOC_H2")              # Hidrojen batarya seviyesi
P_ESD = model.addVars(T, vtype=GRB.CONTINUOUS, name="P_ESD")                # ESD gücü
SOC_ESD = model.addVars(T, vtype=GRB.CONTINUOUS, name="SOC_ESD")             # ESD seviyesi

# Amaç Fonksiyonu: Toplam maliyetin minimize edilmesi
model.setObjective(gp.quicksum(
    P_grid[t] * C_grid[t] - P_sell[t] * C_grid[t] # Satış fiyatı olarak spot fiyatı kullanıyoruz
    for t in range(T)
), GRB.MINIMIZE)

# Kısıtlar:

# 1. Güç Dengesi
for t in range(T):
    model.addConstr(P_demand[t] == P_PV[t] + P_grid[t] + P_fuel_cell[t] - P_sell[t] - P_electrolyzer[t] + P_ESD[t])

# 2. Hidrojen Bataryası Seviyesi Dinamiği
for t in range(T):
    if t == 0:  # Başlangıç durumu
        model.addConstr(SOC_H2[t] == SOC_H2_0 + eta_electrolyzer * P_electrolyzer[t] 
                        - P_fuel_cell[t] / eta_fuel_cell)
    else:
        model.addConstr(SOC_H2[t] == SOC_H2[t-1] + eta_electrolyzer * P_electrolyzer[t] 
                        - P_fuel_cell[t] / eta_fuel_cell)

for t in range(T):
    if C_grid[t] > threshold_price:  # Eğer spot fiyat threshold'dan büyükse enerji satılabilir
        # Fazla PV ve ESD'den satış yapılabilir
        model.addConstr(P_sell[t] <= P_PV[t] + (SOC_H2[t] - SOC_H2_min) + (SOC_ESD[t] - SOC_ESD_min)) 
    else:
        model.addConstr(P_sell[t] == 0)  # Eşik fiyatın altında olduğunda satış yapılmaz

# 3. ESD'nin Şarj/Düşüş Durumu
for t in range(T):
    if t == 0:  # Başlangıç durumu
        model.addConstr(SOC_ESD[t] == SOC_ESD_0 + P_ESD[t])  # ESD'nin şarj durumu
        model.addConstr(P_ESD[t] <= SOC_ESD_max - SOC_ESD_0)  # Başlangıç için şarj sınırı
        model.addConstr(P_ESD[t] >= -(SOC_ESD_0 - SOC_ESD_min))  # Başlangıç için deşarj sınırı
    else:
        model.addConstr(SOC_ESD[t] == SOC_ESD[t-1] + P_ESD[t])  # ESD'nin şarj durumu
        model.addConstr(P_ESD[t] <= SOC_ESD_max - SOC_ESD[t-1])  # Şarj sınırı
        model.addConstr(P_ESD[t] >= -(SOC_ESD[t-1] - SOC_ESD_min))  # Deşarj sınırı

# 4. Kapasite Sınırları
for t in range(T):
    model.addConstr(SOC_H2[t] <= SOC_H2_max)
    model.addConstr(SOC_H2[t] >= SOC_H2_min)
    model.addConstr(SOC_ESD[t] <= SOC_ESD_max)
    model.addConstr(SOC_ESD[t] >= SOC_ESD_min)

# 5. Şebekeye Satış Sınırı (Fazla PV Enerjisi ve Depolama Enerjisi Satılabilir, Eşik Fiyatına Göre)
for t in range(T):
    # Enerji satış koşulunu, eşik fiyatı ile spot fiyatları karşılaştırarak belirleyelim
    if C_grid[t] > threshold_price:  # Eğer spot fiyat threshold'dan büyükse enerji satılabilir
        model.addConstr(P_sell[t] <= P_PV[t] + (SOC_H2[t] - SOC_H2_min) + (SOC_ESD[t] - SOC_ESD_min))  # Fazla PV, batarya ve ESD'den satış
    else:
        model.addConstr(P_sell[t] == 0)  # Eşik fiyatın altında olduğunda satış yapılmaz

# 5. Negatif Güç Akışlarını Önleme
for t in range(T):
    model.addConstr(P_grid[t] >= 0)
    model.addConstr(P_sell[t] >= 0)
    model.addConstr(P_electrolyzer[t] >= 0)
    model.addConstr(P_fuel_cell[t] >= 0)
    #model.addConstr(P_ESD[t] >= -SOC_ESD[t-1])  # ESD'nin negatif gücü

# Modeli çöz
model.optimize()

# Çözümün Görselleştirilmesi
if model.status == GRB.OPTIMAL:
    total_cost = model.objVal
    print(f"Total Cost (Objective Function Value): {total_cost} USD")
    hours = range(T)
    P_grid_sol = [P_grid[t].x for t in hours]
    P_sell_sol = [P_sell[t].x for t in hours]
    SOC_H2_sol = [SOC_H2[t].x for t in hours]
    P_electrolyzer_sol = [P_electrolyzer[t].x for t in hours]
    P_fuel_cell_sol = [P_fuel_cell[t].x for t in hours]
    P_ESD_sol = [P_ESD[t].x for t in hours]
    SOC_ESD_sol = [SOC_ESD[t].x for t in hours]
    
    # Enerji Akışlarının Grafiklerle Gösterilmesi
    plt.figure(figsize=(12, 6))
    
    # Grafik 1: Şebekeye Satış, ESD ve PV Enerjisi
    plt.subplot(1, 2, 1)
    plt.plot(hours, P_grid_sol, label="Energy from Grid", color="blue")
    plt.plot(hours, P_sell_sol, label="Energy Sold to Grid", color="green")
    plt.plot(hours, SOC_H2_sol, label="Hydrogen Battery Level", color="red")
    plt.plot(hours, P_electrolyzer_sol, label="Electrolyzer Power", color="purple")
    plt.plot(hours, P_fuel_cell_sol, label="Fuel Cell Power", color="orange")
    plt.plot(hours, SOC_ESD_sol, label="Energy Storage Device Power", color="brown")
    plt.xlabel("Hour")
    plt.ylabel("Energy (kW/kWh)")
    plt.title("Energy Flows in the System")
    plt.legend()
    plt.grid()

    # Grafik 2: Spot Fiyatlar ve Şebekeye Satış
    fig, ax1 = plt.subplots()

    # Spot Grid Fiyatı: ax1 üzerinde
    ax1.plot(hours, C_grid, label="Spot Grid Price (USD/kWh)", color="black")
    ax1.set_xlabel("Hour")
    ax1.set_ylabel("Price (USD/kWh)", color="black")
    ax1.tick_params(axis='y', labelcolor="black")
    ax1.grid()

    # Eşik Fiyatı: ax1 üzerinde gösteriliyor
    ax1.axhline(y=threshold_price, color="red", linestyle="--", label="Threshold Price")

    # Enerji Satışı: ax2 üzerinde
    ax2 = ax1.twinx()  # ax1 ile aynı x eksenini paylaşacak yeni bir y ekseni
    ax2.plot(hours, P_sell_sol, label="Energy Sold to Grid", color="green")
    ax2.set_ylabel("Energy (kW)", color="green")
    ax2.tick_params(axis='y', labelcolor="green")

    plt.title("Spot Prices and Energy Sale Conditions")
    plt.legend()
    plt.show()

# Çözümün Sayısal Özetini Al
if model.status == GRB.OPTIMAL:
    total_cost = model.objVal
    print(f"Toplam Maliyet: {total_cost:.2f} USD")
    
    # Çözümdeki verileri al
    P_grid_sol = [P_grid[t].x for t in range(T)]
    P_sell_sol = [P_sell[t].x for t in range(T)]
    SOC_H2_sol = [SOC_H2[t].x for t in range(T)]
    P_electrolyzer_sol = [P_electrolyzer[t].x for t in range(T)]
    P_fuel_cell_sol = [P_fuel_cell[t].x for t in range(T)]
    P_ESD_sol = [P_ESD[t].x for t in range(T)]
    SOC_ESD_sol = [SOC_ESD[t].x for t in range(T)]

    # Tabloyu oluştur
    print("\nSaat | Şebekeye Satış (kW) | Şebekeden Alınan Enerji (kW) | Elektrolizör Gücü (kW) | Yakıt Hücresi Gücü (kW) | ESD Gücü (kW) | SOC_H2 (kWh) | SOC_ESD (kWh) | Spot Fiyat (USD/kWh)")
    for t in range(T):
        print(f"{t} | {P_sell_sol[t]:.2f} | {P_grid_sol[t]:.2f} | {P_electrolyzer_sol[t]:.2f} | {P_fuel_cell_sol[t]:.2f} | {P_ESD_sol[t]:.2f} | {SOC_H2_sol[t]:.2f} | {SOC_ESD_sol[t]:.2f} | {C_grid[t]:.2f}")