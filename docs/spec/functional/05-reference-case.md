# 5 Referenzfall

Entwicklungstemplate, nicht Teil der allgemeinen Anforderungen. Instanzdaten stehen unter `config/`.

- Ein Einfamilienhaus, Mehrsplit-Klimaanlage mit sieben Innengeräten (Wandgeräte) und einem Außengerät.
- Räume und Fläche: Wohnen 30 m², Keller 30 m², Schlafen 6 m², Isa, Celle, Jelle und Bad je 12 m².
- Außengerät: Pmin 1,3 kW, Pmax 3,3 kW.
- Wärmeverlust des Hauses UA ≈ 0,115 kW/K (Energieausweis bestätigt), Kapazität ≈ 3 bis 4 kWh_el/K (Schätzung).
- Fensterreiche Räume (Wohnen, Isa) heizen sich bei Sonne selbst auf.

## Geräteeigenschaften, die die Funktion bestimmen

- Heizen und Kühlen an verschiedenen Innengeräten gleichzeitig führt zum Konflikt am Außengerät.
- Nach einem Moduswechsel setzt das Gerät seinen eigenen gemerkten Sollwert, daher muss er neu gesetzt werden.
- Im Lüften und Entfeuchten fehlt der Sollwert, die Gerätetemperatur bleibt.
- Die Gerätetemperatur kommt in ganzen Grad.
- Alle sieben Geräte im Lüften: etwa 85 W gesamt.
