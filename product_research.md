# Architettura e Sviluppo di una WebApp Astrologica Dedicata all'Analisi Natale e Previsionale

La realizzazione di un'applicazione web orientata all'elaborazione di temi natali e transiti previsionali richiede un'integrazione rigorosa tra calcolo astronomico deterministico di precisione, algoritmi di domificazione e motori di sintesi semantica basati su modelli linguistici generativi. L'obiettivo primario consiste nel creare un'infrastruttura accessibile a costo zero per volumi personali (30-40 richieste mensili), garantendo al contempo un'architettura modulare in grado di scalare economicamente qualora i volumi operativi dovessero aumentare.

---

## 1. Analisi Comparativa delle Soluzioni e dei Progetti di Riferimento

La scelta architetturale per la computazione astrologica si articola principalmente tra l'impiego di API gestite di terze parti e il deployment di un motore di calcolo open source self-hosted.

| Soluzione / Repository | Tipologia Architetturale | Licenza / Modello di Costo | Accuratezza Computazionale | Funzionalità di Output e Integrazione | Vincoli e Limitazioni Operative |
| --- | --- | --- | --- | --- | --- |
| **FreeAstroAPI** | API REST esterna su cloud gestito | Freemium (Tier gratuito con 80 req/giorno) | Elevata (Basata su JPL e Swiss Ephemeris) | Risposte JSON tipizzate, grafici SVG/PNG tematici | Dipendenza da server terzi; endpoint di transito avanzati vincolati a piani superiori. |
| **Astrologer-API** (g-battaglia) | Wrapper API REST sviluppato in FastAPI | AGPL-3.0 / Open Source | Massima (Motore Kerykeion su Swiss Ephemeris) | Dati JSON grezzi, SVG vettoriali, contesto XML per LLM | Necessita di un'istanza server Python per l'hosting del runtime. |
| **Zodiac-Engine** (gsinghjay) | WebApp monolitica (FastAPI, HTMX, Bootstrap) | Open Source | Massima (Libreria Kerykeion) | UI responsive, rendering SVG, tabelle dati, prompt AI integrati | Focalizzato prevalentemente sul tema natale; necessita di estensioni per i transiti distribuiti. |
| **chart2txt** (simpolism) | Modulo di elaborazione per TypeScript / Node.js | MIT / Open Source | Dipendente dai dati di ingresso | Rilevamento pattern complessi (Stellium, Grand Trine, dispositori) | Motore analitico puro; non calcola direttamente le effemeridi geocentriche. |
| **Pyswisseph / Stellium** | Binding Python del motore C Swiss Ephemeris | AGPL-3.0 / LGPL | Massima (Standard di riferimento Astrodienst AG) | Calcolo puro di coordinate, velocità, cuspidi, nodi ed eclissi | Richiede l'implementazione completa del layer applicativo e dei modelli dati. |

### Valutazione di FreeAstroAPI

FreeAstroAPI rappresenta una soluzione rapida per ottenere coordinate planetarie, cuspidi Placidus e geometrie d'aspetto attraverso un'unica chiamata REST autenticata. Il piano gratuito offre 80 richieste giornaliere, una quota ampiamente compatibile con un fabbisogno personale di poche decine di consultazioni mensili. Tuttavia, il monitoraggio articolato dei transiti su quattro date distinte nel mese, unito all'individuazione puntuale delle lunazioni, comporterebbe molteplici interrogazioni per ogni singolo report, avvicinandosi ai tetti di frequenza del tier free e limitando la flessibilità nel personalizzare gli orbi o calcolare parametri specifici come i governatori tradizionali.

### Valutazione di Astrologer-API e Kerykeion

La libreria open source `Kerykeion`, alla base del progetto `Astrologer-API`, costituisce il nucleo algoritmico più idoneo per un'applicazione autonoma. Sviluppata in Python sui binding di Swiss Ephemeris (`pyswisseph`), gestisce con precisione astronomica il calcolo delle coordinate eclittiche apparenti, la domificazione Placidus, la velocità giornaliera dei pianeti per il rilevamento istantaneo del moto retrogrado e la comparazione tra due soggetti distinti per estrarre gli aspetti di transito rispetto alla carta natale. La presenza di serializzatori ottimizzati per contesti AI permette inoltre di strutturare l'output per l'elaborazione testuale.

### Valutazione di Zodiac-Engine e chart2txt

Il progetto `Zodiac-Engine` fornisce un modello architetturale collaudato per interfacciare il backend computazionale di Kerykeion con un frontend reattivo e con API di modelli linguistici. Parallelamente, `chart2txt` illustra come strutturare i dati geometrici in entità relazionali chiare, come catene di dominanza planetaria, dispositori finali e configurazioni d'aspetto maggiori. L'unione concettuale di questi due approcci consente di alimentare i prompt LLM con dati esatti e pre-aggregati, eliminando alla radice il rischio di allucinazioni matematiche da parte del modello.

---

## 2. Stack Tecnologico e Servizi Selezionati

L'architettura raccomandata adotta un paradigma disaccoppiato o monolitico modulare basato interamente su tecnologie aperte e risorse cloud gratuite.

### Backend e Motore Astronomico

Il backend è realizzato in Python 3.11+ sfruttando il framework asincrono **FastAPI**. FastAPI garantisce elevate prestazioni computazionali, documentazione interattiva OpenAPI nativa e una rigorosa validazione dei dati di input e output tramite modelli Pydantic.

Il calcolo delle effemeridi viene delegato a **Kerykeion v5** e ai binding diretti di **pyswisseph**, che incorporano i file compressi delle effemeridi Moshier e Swiss Ephemeris per determinare le posizioni dei corpi celesti e delle cuspidi senza dover interrogare server remoti.

La conversione del luogo di nascita in coordinate geografiche avviene tramite la libreria `geopy` interfacciata con il servizio gratuito OpenStreetMap (Nominatim), implementando un layer di memorizzazione nella cache per evitare chiamate ridondanti. L'identificazione del fuso orario storico e del regime di ora legale (DST) alla data di nascita è gestita localmente mediante il pacchetto `timezonefinder` in combinazione con il modulo standard `zoneinfo`, assicurando la massima accuratezza temporale a costo zero.

### Strato di Intelligenza Artificiale per la Reportistica

La generazione dei testi interpretativi per le 8 sezioni del report è affidata a **Google Gemini 2.0 Flash** (o 1.5 Flash) tramite le API di Google AI Studio. Il tier gratuito di Google offre 15 richieste al minuto (RPM), 1 milione di token al minuto (TPM) e fino a 1.500 richieste giornaliere senza alcun costo, fornendo una quota ampiamente superiore alle 30-40 richieste mensili richieste. L'architettura prevede in alternativa la possibilità di reindirizzare le chiamate verso Groq Cloud (Llama 3.3 70B Free Tier) o verso un modello locale eseguito tramite Ollama in caso di utilizzo offline.

### Frontend e Visualizzazione

L'interfaccia utente può essere implementata direttamente all'interno dell'applicazione FastAPI utilizzando template Jinja2 potenziati da **HTMX** e **Tailwind CSS / DaisyUI**, riprendendo l'architettura snella di Zodiac-Engine, oppure tramite una Single Page Application in **React / Next.js**. La visualizzazione del tema natale sfrutta il generatore vettoriale SVG nativo di Kerykeion, che disegna la mappa a cerchi concentrici con indicazione dei simboli planetari, delle cuspidi e delle linee d'aspetto.

### Hosting e Deployment Gratuito

L'intera suite applicativa può essere distribuita a costo zero su piattaforme cloud moderne:

* **Backend**: Distribuzione su **Render.com** (Free Web Service tier da 512 MB di RAM) o **Hugging Face Spaces** (ambiente Docker/FastAPI gratuito su CPU).
* **Frontend**: Qualora disaccoppiato, hosting su **Vercel** o **Cloudflare Pages**.

---

## 3. Dati Tecnici, Algoritmi Astrologici e Regole di Dominio

L'elaborazione dei dati si articola in una prima fase deterministica di estrazione del tema natale (eseguita una sola volta) e in una seconda fase di aggregazione dinamica dei transiti del mese.

| Componente Analitica | Parametri Astronomici Estratti | Regole di Associazione e Dominio |
| --- | --- | --- |
| **Tema Natale (Radix)** | Ascendente ($ASC$), Medio Cielo ($MC$), 12 cuspidi Placidus, posizioni di 10 pianeti e Nodi Lunari. | Domificazione Placidus standard; calcolo aspetti con orbi natali ($\pm 6.0^\circ$ a $\pm 8.0^\circ$). |
| **Area Amore** | Venere, Marte, Luna (segno, grado, casa, aspetti); V Casa e VII Casa (segno cuspide, pianeti interni, governatori). | Determinazione dei governatori (Toro/Bilancia $\to$ Venere; Ariete/Scorpione $\to$ Marte/Plutone; Cancro $\to$ Luna; Leone $\to$ Sole). |
| **Area Lavoro** | Medio Cielo ($MC$), X Casa, VI Casa, II Casa (segni, pianeti presenti, governatori, aspetti ai pianeti natali). | Focus su vocazione ($MC$/X), routine professionale (VI), capacità di monetizzazione e talenti pratici (II). |
| **Area Denaro** | II Casa, VIII Casa (segni, pianeti, governatori); stato cosmico e aspetti di Venere, Giove, Saturno. | Focus su flussi di cassa personali (II), investimenti, debiti, eredità e risorse terze (VIII), espansione (Giove), stabilità (Saturno). |
| **Area Benessere** | Ascendente ($ASC$), Governatore dell'$ASC$, VI Casa (segno, governatore); stato cosmico e aspetti di Marte, Saturno e Luna. | Costituzione e vitalità ($ASC$), somatizzazioni e gestione della salute quotidiana (VI), livelli energetici (Marte), stress/struttura (Saturno), equilibrio emotivo (Luna). |

### Governatori Tradizionali e Moderni

Il sistema implementa una mappatura duale per la determinazione dei governatori delle case astrologiche:

* **Ariete**: Marte (Tradizionale e Moderno).
* **Toro**: Venere (Tradizionale e Moderno).
* **Gemelli**: Mercurio (Tradizionale e Moderno).
* **Cancro**: Luna (Tradizionale e Moderno).
* **Leone**: Sole (Tradizionale e Moderno).
* **Vergine**: Mercurio (Tradizionale e Moderno).
* **Bilancia**: Venere (Tradizionale e Moderno).
* **Scorpione**: Marte (Tradizionale); Plutone con co-governatore Marte (Moderno).
* **Sagittario**: Giove (Tradizionale e Moderno).
* **Capricorno**: Saturno (Tradizionale e Moderno).
* **Acquario**: Saturno (Tradizionale); Urano con co-governatore Saturno (Moderno).
* **Pesci**: Giove (Tradizionale); Nettuno con co-governatore Giove (Moderno).

### Motore Computazionale dei Transiti Mensili

Per replicare fedelmente l'analisi dei transiti tipica di ambienti professionali quali *Astro.com*, l'algoritmo applica un processo di campionamento e tracciamento eventi:

1. **Campionamento Multi-Data**: L'algoritmo calcola le coordinate planetarie in quattro momenti specifici del mese richiesto: il giorno 1 alle 12:00 UTC ($T_1$), il giorno 10 alle 12:00 UTC ($T_2$), il giorno 20 alle 12:00 UTC ($T_3$) e l'ultimo giorno del mese alle 12:00 UTC ($T_4$).
2. **Classificazione dei Pianeti**:
* *Pianeti Veloci*: Sole, Mercurio, Venere, Marte.
* *Pianeti Lenti*: Giove, Saturno, Urano, Nettuno, Plutone.


3. **Rilevamento Retrogradazioni**: Dalla velocità longitudinale $\frac{d\lambda}{dt}$ fornita da Swiss Ephemeris, il sistema verifica se $\frac{d\lambda}{dt} < 0$. In caso positivo, il corpo viene marcato come retrogrado ($R$), registrando le date di stazionamento in cui la velocità inverte il proprio segno algebrico.
4. **Ingressi nelle Case Natali**: Per ogni intervallo temporale compreso tra $T_i$ e $T_{i+1}$, l'algoritmo verifica se la coordinata eclittica di un pianeta in transito $\lambda_{\text{transito}}$ attraversa la longitudine di una delle 12 cuspidi natali Placidus, registrando l'evento di ingresso nella casa corrispondente.
5. **Aspetti Transito-Natale**: Il motore calcola la distanza angolare tra le posizioni dei pianeti in transito e le coordinate dei punti natali ($ASC, MC$, pianeti radix). Gli aspetti maggiori (Congiunzione $0^\circ$, Sestile $60^\circ$, Quadrato $90^\circ$, Trigono $120^\circ$, Opposizione $180^\circ$) vengono considerati attivi applicando un orbe ristretto per i transiti, compreso tra $\pm 1.5^\circ$ e $\pm 2.5^\circ$.
6. **Rilevamento di Lune Nuove e Lune Piene**: La fase lunare viene monitorata attraverso la differenza angolare $\Delta \lambda = (\lambda_{\text{Luna}} - \lambda_{\text{Sole}}) \pmod{360^\circ}$. Mediante un algoritmo di bisezione temporale sull'intervallo mensile, il sistema individua il momento esatto in cui:
* *Novilunio (Luna Nuova)*: $\Delta \lambda = 0^\circ$.
* *Plenilunio (Luna Piena)*: $\Delta \lambda = 180^\circ$.
Per ciascuna lunazione vengono annotate la data precisa, l'ora UTC, il grado zodiacale esatto e la casa natale su cui cade l'evento.



---

## 4. Struttura del Report Finale e Ingegnerizzazione dei Prompt

Tutti i dati estratti dal motore astronomico vengono serializzati in un payload JSON strutturato che funge da contesto esclusivo per il modello linguistico. Questo approccio disaccoppia la computazione dalla sintesi testuale, garantendo coerenza interpretativa e aderenza alle 8 sezioni prefissate.

| Sezione del Report | Fonti Dati Fornite all'AI | Focus Interpretativo |
| --- | --- | --- |
| **1. Energia Generale del Mese** | Transiti dei pianeti lenti su case angolari e pianeti personali; pianeti retrogradi attivi. | Quadro sistemico del periodo, clima psicologico di fondo, tematiche evolutive dominanti. |
| **2. Amore** | Condizione di Venere, Marte, Luna natali; transiti attivi su V e VII Casa; aspetti di transito a Venere/Marte radix. | Relazioni affettive, desideri emotivi, dinamiche di coppia, incontri e chiarimenti. |
| **3. Lavoro** | $MC$, VI e X Casa natali e governatori; transiti su $MC$/X/VI casa; aspetti a Mercurio, Marte, Saturno radix. | Obiettivi professionali, concentrazione, dinamiche contrattuali, rapporti con colleghi e gerarchie. |
| **4. Denaro** | II e VIII Casa natali e governatori; transiti su II/VIII casa; aspetti transitanti a Giove e Saturno natali. | Gestione delle entrate, investimenti, spese programmate o impreviste, trattative economiche. |
| **5. Benessere** | $ASC$, Governatore $ASC$, VI Casa; transiti su $ASC$ e VI casa; aspetti transitanti a Marte, Saturno e Luna. | Vitalità psico-fisica, gestione dello stress, bioritmi, cura del corpo e recupero delle energie. |
| **6. Giorni Favorevoli** | Elenco date esatte con aspetti armonici esatti (Trigoni, Sestili, Congiunzioni positive) tra transiti e punti natali; lunazioni favorevoli. | Momenti propizi per accordi, iniziative, colloqui, decisioni importanti ed espansione. |
| **7. Giorni di Attenzione** | Elenco date esatte con aspetti disarmonici esatti (Quadrati, Opposizioni, passaggi marziani/saturnini tesi); stazionamenti retrogradi. | Finestre temporali delicate per comunicazioni, decisioni impulsive o gestione dei conflitti. |
| **8. Consiglio Astrologico Finale** | Sintesi sinergica tra la casa natale toccata dalle lunazioni del mese e l'assetto planetario complessivo. | Indicazione strategica, etica e motivazionale per orientare le azioni del mese. |

Il prompt di sistema istruisce il modello a operare con un registro professionale, evitando approcci fatalistici e basando ogni affermazione esclusivamente sui dati astronomici e natali forniti nel payload, citando esplicitamente le date dei transiti e le posizioni coinvolte nelle relative sezioni.

---

## 5. Roadmap Operativa di Sviluppo

Lo sviluppo della webapp si articola in cinque fasi operative consequenziali progettate per convalidare progressivamente l'accuratezza dei calcoli e la robustezza dell'infrastruttura.

### Fase 1: Setup dell'Ambiente e Core Engine Natale

La fase iniziale prevede la configurazione dell'ambiente di sviluppo in Python 3.11 con gestione dei pacchetti tramite Poetry o UV. Viene implementato il modulo di geocodifica locale con memorizzazione su SQLite dei toponimi per limitare le interrogazioni a Nominatim. Viene integrata la libreria Kerykeion per la creazione dell'oggetto `AstrologicalSubject`, consentendo il calcolo istantaneo di pianeti, cuspidi Placidus e aspetti natali con orbi personalizzabili.

### Fase 2: Sviluppo del Modulo Transiti e Lunazioni

La seconda fase introduce la classe `MonthlyTransitEngine`, deputata all'elaborazione temporale del mese di analisi. Il modulo genera le effemeridi per i quattro giorni campionati (1, 10, 20 e ultimo del mese), valuta le variazioni di segno e velocità per identificare i moti retrogradi e calcola gli ingressi dei pianeti nelle 12 case del tema natale. Viene integrato l'algoritmo di calcolo delle lunazioni per localizzare con precisione al minuto i noviluni e i pleniluni mensili.

### Fase 3: Regole di Dominio e Integrazione AI

In questa fase viene implementata la logica di attribuzione dei governatori (tradizionali e moderni) per ciascuna cuspide. I dati vengono clusterizzati nei quattro ambiti tematici (Amore, Lavoro, Denaro, Benessere). Viene sviluppato il client asincrono verso Google AI Studio (Gemini 2.0 Flash API), con validazione dello schema di risposta JSON tramite Pydantic e gestione dei retry automatici in caso di rate limit.

### Fase 4: Sviluppo Frontend e Visualizzazione

La quarta fase è dedicata all'interfaccia utente. Viene realizzato il form di inserimento dati (nome, data, ora, luogo di nascita e mese di analisi). Viene integrato il visualizzatore SVG per mostrare il grafico della carta natale generato da Kerykeion, arricchito da tabelle riassuntive delle posizioni planetarie e delle cuspidi. L'interfaccia organizza i testi del report nelle 8 sezioni stabilite, fornendo controlli per l'esportazione in formato PDF e Markdown.

### Fase 5: Validazione, Benchmark e Rilascio

L'ultima fase prevede il test di conformità matematica: i dati di posizioni planetarie, cuspidi ed eventi di transito vengono confrontati con i valori di riferimento forniti dalla sezione *Natal chart and transits* di *Astro.com*. Completata la validazione, l'applicazione viene containerizzata tramite Docker e distribuita gratuitamente su Render.com o Hugging Face Spaces.

---

## 6. Analisi Economica e Scalabilità dei Costi

L'architettura proposta garantisce l'assenza totale di costi vivi per l'utilizzo personale di 30-40 richieste al mese. La tabella illustra l'impatto economico all'aumentare dei volumi operativi, delineando le soglie di spesa previste in caso di espansione.

| Componente Architetturale | Volume Base (30-40 Req/Mese) | Volume Medio (1.000 Req/Mese) | Volume Elevato (10.000 Req/Mese) | Volume Enterprise (50.000+ Req/Mese) |
| --- | --- | --- | --- | --- |
| **Infrastruttura Server Backend** | **0,00 €** (Render / Hugging Face Free Tier) | **0,00 €** (Render Free Allowance) | **7,00 € / mese** (Render Individual / VPS Hetzner) | **20,00 - 45,00 € / mese** (VPS dedicato multi-core Scaleway / Hetzner) |
| **Calcolo Astronomico (Swiss Ephemeris)** | **0,00 €** (Elaborazione locale CPU con Kerykeion) | **0,00 €** (Elaborazione locale CPU) | **0,00 €** (Elaborazione locale CPU) | **0,00 €** (Elaborazione locale multi-worker FastAPI) |
| **Geocoding & Timezone** | **0,00 €** (Nominatim con cache locale + timezonefinder) | **0,00 €** (Cache SQLite toponimi) | **0,00 €** (Database GeoNames scaricato in locale) | **0,00 €** (GeoNames su istanza PostgreSQL/PostGIS locale) |
| **Generazione Testi AI (Gemini Flash)** | **0,00 €** (Google AI Studio Free Tier: 1.500 req/giorno) | **0,00 €** (Entro i limiti del tier gratuito) | **~1,20 - 1,80 € / mese** (Tariffa a consumo: ~0,15 € / 1M token) | **~6,00 - 12,00 € / mese** (Tariffa a consumo su API Gemini Flash) |
| **Hosting Frontend** | **0,00 €** (Cloudflare Pages / Vercel Free) | **0,00 €** (Cloudflare Pages Free) | **0,00 €** (Cloudflare Pages Free) | **0,00 - 20,00 € / mese** (Cloudflare Pages / Vercel Pro) |
| **Spesa Totale Stimata** | **0,00 € / mese** | **0,00 € / mese** | **~8,20 - 8,80 € / mese** | **~26,00 - 77,00 € / mese** |

Poiché il motore di calcolo astronomico risiede interamente nel runtime applicativo locale tramite librerie open source, l'infrastruttura non dipende da licenze a pagamento o quote API esterne per le effemeridi. La sola componente soggetta a tariffazione a consumo per volumi industriali riguarda i token del modello linguistico. Tuttavia, grazie all'elevata efficienza economica di Gemini Flash (o in alternativa dei modelli open source serviti tramite Groq o istanze vLLM dedicate), l'elaborazione di migliaia di report mensili completi comporta costi marginali estremamente ridotti.

---

## 7. Conclusioni

L'impostazione architetturale delineata soddisfa integralmente i requisiti posti dal progetto:

* Assicura la totale assenza di costi ricorrenti per l'uso personale, facendo leva su librerie aperte e sui tier gratuiti dei moderni provider cloud.
* Esegue l'estrazione statica e precisa del tema natale (Placidus, angoli cardinali, posizioni dei pianeti, cuspidi e aspetti) conformemente alla tradizione occidentale.
* Raggruppa i parametri astrologici e i rispettivi governatori tradizionali e moderni nelle quattro aree di indagine (Amore, Lavoro, Denaro, Benessere).
* Replica l'accuratezza previsionale di strumenti di riferimento come *Astro.com*, campionando i transiti sui giorni 1, 10, 20 e fine mese con tracciamento di pianeti veloci, lenti, retrogradazioni, ingressi nelle case, aspetti al radix e fasi lunari.
* Produce un report strutturato secondo le 8 sezioni previste, fornendo un'applicazione robusta, autosufficiente e facilmente estendibile nel tempo.
