# `core.chat` + Storage API becsatlakozás, verziózás, upstream terv

> Státusz: **terv**. Utolsó verzióellenőrzés: **2026-09-22**.
> Cél: a Vambery agent a hivatalos Superset extension-API-kra álljon át, a jelenlegi
> 6.1.x-es éles telepítés törése nélkül.

## Kontextus

- **A mi termékünk:** Vambery AI Agent (`integrityauthority.vambery-ai-assistant`, **v0.5.2**).
  Teljes agent: backend + LLM + 18 tool + planner-checker loop. Jelenleg
  `views.registerView(..., "sqllab.rightSidebar", ...)`-tal mountol, SQL Lab-only.
- **SIP-214 (issue [#41059](https://github.com/apache/superset/issues/41059)):** hivatalos
  `core.chat` contribution — **csak UI mounting-szerződés**, nulla agent-logika.
  PR [#41205](https://github.com/apache/superset/pull/41205), merge: 2026-06-25 (`a90c8e0`).
- **Storage API:** PR [#39171](https://github.com/apache/superset/pull/39171),
  merge: 2026-07-21 (`34ebe3d`).
- **Alapelv:** a SIP-214 a *keret*, a Vambery a *kép*. A backend/agent 100%-ban a miénk
  marad — ez a moat, ebből upstream semmi nincs.

---

## 0) Verzióállás (2026-09-22) — a legfontosabb tény

**Az egyetlen kiadott verzió továbbra is a 6.1.0 (2026-05-13).** Azóta nincs új app-release.
Létezik viszont már **`6.2` és `7.0` release-előkészítő branch** — de **egyikből sincs
még RC tag sem**.

A két nekünk fontos funkció **külön minor verzióba került**:

| Base | `chat` + `navigation` | `storage` | Branch head | Kiadva? |
|---|---|---|---|---|
| **6.1** (éles nálunk) | ❌ | ❌ | 2026-07-20 | ✅ 6.1.0, 2026-05-13 |
| **6.2** (branch) | ✅ | ❌ | 2026-09-01 | ❌ nincs tag |
| **7.0** (branch) | ✅ | ✅ | 2026-09-20 | ❌ nincs tag |
| master | ✅ | ✅ | 2026-09-22 | — |

**Következmények:**
1. A `core.chat` **6.2-től** elérhető — de csak buildből, mert nincs kiadás.
2. A Storage API **NEM került be a 6.2-be**, csak a **7.0-ba**. Vagyis a két funkció
   nem egyszerre érkezik → a saját `conversationStorage` fallbackre **hosszabb távon**
   szükség lesz, mint gondoltuk.
3. Stock telepítésen ma **semmi** nincs ezekből — a 6.1.0 az egyetlen kiadott verzió.

---

## 1) A tényleges API-k (kiolvasva a `6.2` branchből, nem PR-összefoglalóból)

### `chat` namespace

```ts
export interface Chat { id: string; name: string; description?: string; }
export type DisplayMode = 'floating' | 'panel';

export declare function registerChat(
  chat: Chat,
  trigger: ComponentType,   // összecsukott buborék belépési pont
  panel: ComponentType,     // a panel, mindkét display módban ez renderelődik
): Disposable;

export declare function getChat(): Chat | undefined;
export declare function open(): void;
export declare function close(): void;
export declare function isOpen(): boolean;
export declare function getDisplayMode(): DisplayMode;
export declare function setDisplayMode(displayMode: DisplayMode): void;

export declare const onDidRegisterChat: Event<Chat>;
export declare const onDidUnregisterChat: Event<Chat>;
export declare const onDidOpen: Event<void>;
export declare const onDidClose: Event<void>;
export declare const onDidChangeDisplayMode: Event<DisplayMode>;
export declare const onDidResizePanel: Event<{ width: number }>;
```

Manifest oldalon: `Contributions.chat?: Chat` — vagyis az `extension.json`-be egy `chat`
kulcs kerül, **extensionönként legfeljebb egy** (a host egyszerre egy chatet futtat;
a legutóbb regisztrált nyer).

### `navigation` namespace — **figyelem, 10 érték, nem 3**

```ts
export type Page =
  | 'dashboard' | 'dashboard_list' | 'explore' | 'chart_list' | 'sqllab'
  | 'query_history' | 'saved_queries' | 'dataset' | 'dataset_list' | 'home';

export declare function getPage(): Page;
export declare const onDidChangePage: Event<Page>;
```

> Korábban 3 értéket feltételeztünk (`dashboard`/`explore`/`sqllab`). Valójában **10** van —
> a gate-elésnél (A3) minden nem-`sqllab` esetet kezelni kell, nem csak kettőt.

### `storage` namespace (csak 7.0+)

Négy tier, extension-namespace-elve:

| Tier | Mi | Megjegyzés |
|---|---|---|
| `local` | böngésző localStorage | per-device, **nincs** `.shared` |
| `session` | böngésző sessionStorage | tab bezárásakor törlődik, **nincs** `.shared` |
| `ephemeral` | szerver-oldali cache | **`ttl` kötelező** minden `set`-nél; van `.shared` |
| `persistent` | **DB-backed** | opcionális **`encrypt`**, támogat `list()`-et; van `.shared` |

> A [superset-core.d.ts](../frontend/src/superset-core.d.ts)-ünk **már illeszkedik** ehhez:
> `local`/`session` `.shared` nélküli `StorageAccessor`, `persistent.list()` és
> `PersistentSetOptions.encrypt` bent van. (A `get`/`set` nálunk generikus
> (`get<T>()`) — ez helyi kényelmi bővítés a felmenő `JsonValue`-hoz képest,
> futásidőben azonos.)

---

## 2) Verziózási stratégia — kétréteges

**(A) ALAPÉRTELMEZÉS, a hivatalosan ajánlott út: capability-detektálás + fallback.**
Az extension stock 6.1.x-en is betölt (régi sidebar + saját storage), és fejlettebb
host-on maguktól kigyúlnak az extrák. Ez az upstream-konform és hatósági szemmel is
biztonságos default — soha nem követeljük meg az unreleased core-t.

**(B) OPT-IN GYORSSÁV: verziózott saját base image.**
Aki a teljes élményt akarja most, `integrityauthority/superset:<ver>` image-et húz.
Fegyelem, különben csapda:
- **Konkrét commitra pinnelni, nem `latest master`-re.** Beszédes tag, pl.
  `6.2.0-dev-20260901-fd55308d`. **A `6.2` branchre pinnelni, ne masterre** — az
  release-előkészítő ág lényegesen stabilabb.
- **Verzió → feature kompatibilitási mátrix** a README-ben (lásd a 0) szakasz tábláját).
- **Security-patch kadencia + rebuild-folyamat** dokumentálva.
- **DB-migrációk**: a 7.0 `persistent` storage Alembic-migrációkat hoz — frissítési és
  visszaállási útvonalat tesztelni.

### Konkrét verzió-ajánlás nekünk

| Környezet | Mire álljunk | Miért |
|---|---|---|
| **Éles** | **maradjon 6.1.x** | ez az egyetlen kiadott verzió; hatósági rendszert nem viszünk unreleased branchre |
| **Dev/teszt** | **pinned build a `6.2` branchből** | itt fejleszthető a `core.chat` migráció; 6.2 a legközelebbi realisztikus cél |
| **Storage API** | kód kész, **alvó** | csak 7.0-ban van; a detektálás miatt 6.1/6.2-n no-op, magától bekapcsol 7.0-n (tesztelés ott) |

---

## 3) Becsatlakozási TODO

### A1. Előkészítés
- [x] Végleges `core.chat` / `navigation` API kiolvasva a `6.2` branchből (lásd 1. szakasz).
- [x] Verzióállás tisztázva: chat→6.2, storage→7.0, kiadás egyikből sincs.
- [ ] Dev/teszt pinned image build a `6.2` branchből (tag: `6.2.0-dev-<dátum>-<sha>`).
- [ ] `extension.json` kompatibilitási/`engines` mező eldöntése.

### A2. Regisztráció — dual-registration ✅ **kész (v0.6.0)**
- [x] `index.tsx`: feature-detektálás. `chat.registerChat` → azt; különben fallback
      `views.registerView(..., "sqllab.rightSidebar", ...)`. Namespace import
      (`import * as core`), mert a named `chat` import 6.1-en nem linkelne.
- [x] `VamberyTrigger` komponens (összecsukott buborék). A fejlesztői dokumentáció
      szerint **a trigger felelős a nyitás/zárásért** (`chat.isOpen()/open()/close()`).
- [x] `extension.json`: `chat` contribution a `views` **mellé** (`Contributions.chat`).
- [x] **Nem** hívunk `setDisplayMode()`-ot regisztrációkor — a host megőrzi a user
      display-mode és nyitva/zárva választását újratöltések közt; felülírni ellenséges lenne.

### A3. Oldal-kontextus ✅ **kész (v0.6.0)**
- [x] `ChatPanel` gate-elése — `hostCapabilities.isSqlLabContext()` a `navigation.getPage()`
      fölött. A `safeGetCurrentTab()` minden `sqlLab.*` hívást véd (6.2+-on a namespace
      **dob** rossz oldalról, nem `undefined`-ot ad).
- [x] `navigation.onDidChangePage()` feliratkozás → oldalváltáskor újraszámolás.
- [x] Nem-`sqllab` oldalon: figyelmeztető sáv + letiltott beviteli mező és Küldés gomb,
      ahelyett hogy minden üzenet 400-zal elszállna a backenden.
- [ ] Később: dashboard/explore kontextus tényleges kihasználása (ehhez kell a B2
      upstream page-context bővítés — ma a `getPage()` csak a típust adja).

### A4. UI-illesztés
- [ ] `onDidResizePanel` (`{ width }`) kezelése a fix méretezés helyett.
- [ ] Téma + syntax-highlight ellenőrzése a keskenyebb `floating` buborékban.
- [ ] Conversation storage: oldalanként vagy globálisan tartsuk a beszélgetést?

### A5. Storage API — **implementálva, 7.0-n aktiválódik**

A kód készen áll és 6.1/6.2-n csendben no-op (graceful fallback); a `persistent` tier
megjelenésekor (7.0) magától bekapcsol. Nincs mit halasztani — a *tesztelése* vár 7.0-ra.

- [x] Feature-detektálás (`isStorageAvailable()`) — [conversationStorage.ts](../frontend/src/conversationStorage.ts)
- [x] `superset-core.d.ts` a valós API-ra igazítva (`local`/`session` `.shared` nélkül,
      `persistent.list()`, `PersistentSetOptions.encrypt`)
- [x] Conversation-history a `persistent` tierre, **`encrypt: true`**-val (hatósági környezet)
- [x] Model-preferencia a `local` tierre; megosztott playbookok a `persistent.shared`-re
- [x] Debounce-olt auto-save + tab-scope-olt beszélgetések
      ([useConversationStorage.ts](../frontend/src/useConversationStorage.ts))
- [ ] **Tesztelés 7.0-pinned buildben** (amíg nincs, a kód nem futott éles Storage API-n)

**Ismert, még nyitott apróságok** (nem blokkolók, code review során azonosítva):
- [ ] Kétféle detektálási útvonal: `isStorageAvailable()` a `window.superset.extensions`-t
      nézi, `getStorage()` az importált `extensions.getContext()`-et — ha eltérnek, a
      funkció csendben kikapcsol (fail-safe, de félrevezető).
- [ ] `activePlanState` ref-ként tér vissza a hookból → ref-változás nem triggerel
      re-rendert, így a `ChatPanel` szinkronizáló effectje tab-váltáskor nem biztosan fut le.
- [ ] `saveConversation` load-modify-write az egész conversations mapre → párhuzamos
      példányok felülírhatják egymást.

### A6. Kivezetés (feltételes)
- [ ] Amikor a `core.chat`-es verzió lesz a támogatott minimum: `views.registerView`
      fallback és a régi `extension.json` `views` contribution kivezetése.
- [ ] README + deploy dokumentáció frissítése.

### A7. Teszt
- [ ] 6.2-pinned build: mind a 18 tool + planner működik `core.chat` mountban (SQL Lab).
- [ ] Dashboard/explore/dataset/home: a panel megnyílik, kontextushiány nélkül nem száll el.
- [ ] Fallback ág: stock 6.1.x-en a régi sidebar változatlanul működik.
- [ ] Verziómátrix dokumentálva.

---

## 4) Upstream javaslat (Apache Superset felé)

**Alapelv:** csak azt visszük fel, ami **általánosan** hasznos, a megfelelő helyre
(SIP + PR), rendes tesztekkel — hogy tényleg mergelhető legyen.

### B1. Client Actions / agentic UI manipulation *(elsődleges jelölt)*
- A SIP-214 ezt **explicit kihagyta**, külön Client Actions SIP-re halasztotta.
- Nálunk működő referencia: `set_editor_sql`, `create_chart`, `update_todo`, `ask_user`.
- [ ] Megnézni, van-e már nyitott Client Actions SIP/issue; ha igen, csatlakozni.
- [ ] Ha nincs: általánosított, provider-független action-szerződés javaslata
      (nem a mi konkrét tooljaink, hanem az absztrakció).
- [ ] Teszt-suite + dokumentáció.

### B2. Page-context átadás *(másodlagos jelölt)*
- A `navigation.getPage()` csak a page **típusát** adja, a konkrét azonosítót
  (dashboard id, explore datasource, SQL Lab tab) nem.
- [ ] Javaslat: strukturált, olvasható kontextus minden felületre, Proxy-guardokkal.
- [ ] Tesztek + dokumentáció.

### B3. Ne menjen upstream
- LLM provider absztrakció (Azure/OpenAI/Ollama), planner-checker loop, konkrét
  SQL/chart/dataset tool-implementációk — mind extension-szint.
