// Tests de comportamiento para las tareas T-102..T-104 (T-101 se retiró del benchmark en v4; su test queda por si se reactiva).
// Los tipos nuevos se resuelven por reflexión para que el arnés compile aunque el modelo no los cree.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using UnityEngine;
using UnityEngine.UI;
using Game.Player;
using Game.Items;
using Game.Enemies;
using Game.Combat;

public static class Bench
{
    private static readonly Dictionary<string, object> Results = new Dictionary<string, object>();
    private static readonly List<string> Notes = new List<string>();

    private static void Check(string name, Func<bool> f)
    {
        try { Results[name] = f(); }
        catch (Exception e)
        {
            var inner = e is TargetInvocationException tie && tie.InnerException != null ? tie.InnerException : e;
            Results[name] = false;
            Notes.Add($"{name}: {inner.GetType().Name}: {inner.Message}");
        }
    }

    private static Type FindType(string fullName) =>
        AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetType(fullName)).FirstOrDefault(t => t != null);

    private static Type FindTypeByName(string name) =>
        AppDomain.CurrentDomain.GetAssemblies().SelectMany(a => { try { return a.GetTypes(); } catch { return new Type[0]; } })
            .FirstOrDefault(t => t.Name == name);

    private static IEnumerable<FieldInfo> AllFields(Type t)
    {
        while (t != null && t != typeof(MonoBehaviour) && t != typeof(object))
        {
            foreach (var f in t.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
                yield return f;
            t = t.BaseType;
        }
    }

    /// Simula el Inspector: asigna cada dependencia al primer campo compatible que esté vacío.
    private static Component Add(GameObject go, Type t, params object[] deps)
    {
        return go.AddComponentWith(t, c =>
        {
            foreach (var d in deps)
            {
                var f = AllFields(t).FirstOrDefault(fi => fi.FieldType.IsInstanceOfType(d) && fi.GetValue(c) == null
                                                       && !typeof(Delegate).IsAssignableFrom(fi.FieldType));
                if (f != null) f.SetValue(c, d);
                else Notes.Add($"No encontré un campo de tipo {d.GetType().Name} en {t.Name}");
            }
        });
    }

    private static T Add<T>(GameObject go, params object[] deps) where T : Component => (T)Add(go, typeof(T), deps);

    private static object Prop(object o, string name) =>
        o.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.Public)?.GetValue(o);

    private static int Subscribers(object o, string evt)
    {
        var t = o.GetType();
        while (t != null)
        {
            var f = t.GetField(evt, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
            if (f != null) return (f.GetValue(o) as Delegate)?.GetInvocationList().Length ?? 0;
            t = t.BaseType;
        }
        return -1;
    }

    private static void Subscribe(object o, string evt, Delegate handler)
    {
        var e = o.GetType().GetEvent(evt, BindingFlags.Instance | BindingFlags.Public);
        e.AddEventHandler(o, handler);
    }

    private static void Invoke(object o, string method, params object[] args)
    {
        var t = o.GetType();
        while (t != null)
        {
            var m = t.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly)
                     .FirstOrDefault(mi => mi.Name == method && mi.GetParameters().Length == args.Length);
            if (m != null) { m.Invoke(o, args); return; }
            t = t.BaseType;
        }
        throw new MissingMethodException(o.GetType().Name, method);
    }

    private static bool Near(float a, float b) => Math.Abs(a - b) < 0.011f;

    // ------------------------------------------------------------------ T-101
    private static void T101()
    {
        var barType = FindType("Game.UI.HealthBarUI") ?? FindTypeByName("HealthBarUI");
        Check("clase Game.UI.HealthBarUI existe", () => FindType("Game.UI.HealthBarUI") != null);
        if (barType == null) return;

        var player = Add<PlayerHealth>(new GameObject("Player"));
        var uiGo = new GameObject("UI");
        var image = uiGo.AddComponent<Image>();
        image.fillAmount = 0.123f;
        var bar = (Behaviour)Add(uiGo, barType, player, image);
        Lifecycle.StartPending();

        Check("Start refleja la vida actual (1.0)", () => Near(image.fillAmount, 1f));
        Check("daño 25 → 0.75 (división float)", () => { player.TakeDamage(25); return Near(image.fillAmount, 0.75f); });
        Check("curar 10 → 0.85", () => { player.Heal(10); return Near(image.fillAmount, 0.85f); });
        Check("deshabilitado no reacciona", () => { bar.enabled = false; player.TakeDamage(50); return Near(image.fillAmount, 0.85f); });
        Check("deshabilitado sin suscripciones colgando", () => Subscribers(player, "OnHealthChanged") == 0);
        Check("al rehabilitar vuelve a reaccionar", () => { bar.enabled = true; player.TakeDamage(5); return Near(image.fillAmount, 0.30f); });
        Check("una sola suscripción activa", () => Subscribers(player, "OnHealthChanged") == 1);
        Check("destruir el objeto limpia la suscripción", () => { UnityEngine.Object.Destroy(uiGo); return Subscribers(player, "OnHealthChanged") == 0; });
    }

    // ------------------------------------------------------------------ T-102
    private static void T102()
    {
        Inventory NewInv(out Func<int> events)
        {
            Lifecycle.Reset();
            var inv = Add<Inventory>(new GameObject("Inv"));
            int count = 0;
            inv.OnInventoryChanged += () => count++;
            events = () => count;
            return inv;
        }

        Check("capacidad: nunca más de 10 slots", () =>
        {
            var inv = NewInv(out _);
            int left = inv.AddItem("a", 99 * 12);
            return inv.Slots.Count == 10 && left == 99 * 2;
        });
        Check("capacidad: 11 items distintos → el 11º no cabe", () =>
        {
            var inv = NewInv(out _);
            for (int i = 0; i < 10; i++) inv.AddItem("i" + i, 1);
            return inv.AddItem("extra", 1) == 1 && inv.Slots.Count == 10 && inv.GetCount("extra") == 0;
        });
        Check("quitar 120 de 99+50 → quedan 29", () =>
        {
            var inv = NewInv(out _);
            inv.AddItem("p", 149);
            return inv.RemoveItem("p", 120) && inv.GetCount("p") == 29 && inv.Slots.Count == 1;
        });
        Check("quitar 200 de 99+99+52 → quedan 50", () =>
        {
            var inv = NewInv(out _);
            inv.AddItem("x", 250);
            return inv.RemoveItem("x", 200) && inv.GetCount("x") == 50;
        });
        Check("quitar con stacks intercalados", () =>
        {
            var inv = NewInv(out _);
            inv.AddItem("p", 99); inv.AddItem("q", 5); inv.AddItem("p", 99); inv.AddItem("q", 5);
            return inv.RemoveItem("p", 150) && inv.GetCount("p") == 48 && inv.GetCount("q") == 10;
        });
        Check("quitar sin suficientes → false y sin cambios", () =>
        {
            var inv = NewInv(out var ev);
            inv.AddItem("p", 10);
            int before = ev();
            return !inv.RemoveItem("p", 11) && inv.GetCount("p") == 10 && ev() == before;
        });
        Check("evento al quitar (una vez)", () =>
        {
            var inv = NewInv(out var ev);
            inv.AddItem("p", 149);
            int before = ev();
            inv.RemoveItem("p", 120);
            return ev() == before + 1;
        });
        Check("sin evento si no cambió nada (add 0 / lleno / remove 0)", () =>
        {
            var inv = NewInv(out var ev);
            for (int i = 0; i < 10; i++) inv.AddItem("i" + i, 99);
            int before = ev();
            inv.AddItem("i0", 0);
            inv.AddItem("nuevo", 5);
            inv.RemoveItem("i1", 0);
            return ev() == before;
        });
        Check("el evento llega con el estado ya consistente", () =>
        {
            var inv = NewInv(out _);
            inv.AddItem("p", 149);
            int seen = -1;
            inv.OnInventoryChanged += () => seen = inv.GetCount("p");
            inv.RemoveItem("p", 120);
            return seen == 29;
        });
        Check("quitar justo un stack completo no deja slots vacíos", () =>
        {
            var inv = NewInv(out _);
            inv.AddItem("p", 99); inv.AddItem("q", 3);
            return inv.RemoveItem("p", 99) && inv.Slots.Count == 1 && inv.Slots[0].ItemId == "q" && inv.GetCount("p") == 0;
        });
        Check("quitar un item que no existe → false, sin evento", () =>
        {
            var inv = NewInv(out var ev);
            inv.AddItem("p", 5);
            int before = ev();
            return !inv.RemoveItem("nada", 1) && ev() == before && inv.GetCount("p") == 5;
        });
        Check("vaciar por completo y volver a llenar los 10 slots", () =>
        {
            var inv = NewInv(out _);
            for (int i = 0; i < 10; i++) inv.AddItem("i" + i, 99);
            for (int i = 0; i < 10; i++) if (!inv.RemoveItem("i" + i, 99)) return false;
            if (inv.Slots.Count != 0) return false;
            for (int i = 0; i < 10; i++) if (inv.AddItem("j" + i, 99) != 0) return false;
            return inv.Slots.Count == 10;
        });
        Check("agregar parcial dispara evento una vez y devuelve sobrante", () =>
        {
            var inv = NewInv(out var ev);
            for (int i = 0; i < 9; i++) inv.AddItem("i" + i, 99);
            int before = ev();
            int left = inv.AddItem("z", 150);
            return left == 51 && ev() == before + 1 && inv.GetCount("z") == 99;
        });
        Check("stacks parciales se completan antes de abrir slots", () =>
        {
            var inv = NewInv(out _);
            inv.AddItem("p", 50); inv.AddItem("p", 60);
            return inv.Slots.Count == 2 && inv.Slots[0].Count == 99 && inv.Slots[1].Count == 11;
        });
    }

    // ------------------------------------------------------------------ T-103
    private static void T103()
    {
        var idmg = FindType("Game.Combat.IDamageable") ?? FindTypeByName("IDamageable");
        var enemyType = FindType("Game.Enemies.EnemyHealth") ?? FindTypeByName("EnemyHealth");
        Check("interfaz Game.Combat.IDamageable con TakeDamage(int)", () =>
            FindType("Game.Combat.IDamageable") is Type t && t.IsInterface &&
            t.GetMethod("TakeDamage", new[] { typeof(int) }) != null && t.GetMethods().Length == 1);
        Check("PlayerHealth implementa IDamageable", () => idmg != null && idmg.IsAssignableFrom(typeof(PlayerHealth)));
        Check("clase Game.Enemies.EnemyHealth implementa IDamageable", () =>
            FindType("Game.Enemies.EnemyHealth") is Type t && idmg != null && idmg.IsAssignableFrom(t));

        Check("PlayerHealth conserva su comportamiento", () =>
        {
            Lifecycle.Reset();
            var p = Add<PlayerHealth>(new GameObject("P"));
            p.TakeDamage(30); p.Heal(10); p.TakeDamage(-5); p.TakeDamage(500);
            return p.CurrentHealth == 0 && p.MaxHealth == 100;
        });

        if (enemyType != null)
        {
            Component NewEnemy(out Func<int> died)
            {
                Lifecycle.Reset();
                var e = Add(new GameObject("Enemy"), enemyType);
                int n = 0;
                try { Subscribe(e, "OnDied", (Action)(() => n++)); } catch { Notes.Add("OnDied no es un event Action público"); }
                died = () => n;
                return e;
            }

            Check("vida inicial = GameBalance.EnemyBaseHealth (60)", () =>
                Convert.ToInt32(Prop(NewEnemy(out _), "CurrentHealth")) == 60);
            Check("ignora daño <= 0", () =>
            {
                var e = NewEnemy(out _);
                Invoke(e, "TakeDamage", 0); Invoke(e, "TakeDamage", -7);
                return Convert.ToInt32(Prop(e, "CurrentHealth")) == 60;
            });
            Check("daño parcial y propiedades", () =>
            {
                var e = NewEnemy(out _);
                Invoke(e, "TakeDamage", 25);
                return Convert.ToInt32(Prop(e, "CurrentHealth")) == 35 && Equals(Prop(e, "IsDead"), false);
            });
            Check("muerte: vida 0, IsDead, OnDied una vez", () =>
            {
                var e = NewEnemy(out var died);
                Invoke(e, "TakeDamage", 100);
                Invoke(e, "TakeDamage", 10);
                Invoke(e, "TakeDamage", 10);
                return Convert.ToInt32(Prop(e, "CurrentHealth")) == 0 && Equals(Prop(e, "IsDead"), true) && died() == 1;
            });
            Check("muerte exacta (60) dispara OnDied", () =>
            {
                var e = NewEnemy(out var died);
                Invoke(e, "TakeDamage", 30); Invoke(e, "TakeDamage", 30);
                return died() == 1;
            });
            Check("en OnDied el enemigo ya figura muerto", () =>
            {
                var e = NewEnemy(out _);
                bool ok = false;
                Subscribe(e, "OnDied", (Action)(() => ok = Equals(Prop(e, "IsDead"), true) && Convert.ToInt32(Prop(e, "CurrentHealth")) == 0));
                Invoke(e, "TakeDamage", 500);
                return ok;
            });
            Check("dos enemigos son independientes (sin estado estático)", () =>
            {
                Lifecycle.Reset();
                var a = Add(new GameObject("A"), enemyType);
                var b = Add(new GameObject("B"), enemyType);
                Invoke(a, "TakeDamage", 100);
                return Equals(Prop(a, "IsDead"), true) && Equals(Prop(b, "IsDead"), false) && Convert.ToInt32(Prop(b, "CurrentHealth")) == 60;
            });
            Check("propiedades de solo lectura", () =>
                enemyType.GetProperty("CurrentHealth")?.SetMethod?.IsPublic != true &&
                enemyType.GetProperty("IsDead")?.SetMethod?.IsPublic != true &&
                enemyType.GetProperty("CurrentHealth") != null && enemyType.GetProperty("IsDead") != null);

            Check("proyectil daña a un enemigo y se destruye", () =>
            {
                Lifecycle.Reset();
                var enemyGo = new GameObject("Enemy");
                var e = Add(enemyGo, enemyType);
                var col = enemyGo.AddComponent<Collider>();
                var projGo = new GameObject("Bullet");
                var proj = Add<Projectile>(projGo);
                Invoke(proj, "OnTriggerEnter", col);
                int hp = Convert.ToInt32(Prop(e, "CurrentHealth"));
                return (hp == 50 || hp == 45) && projGo == null;
            });
        }

        Check("proyectil sigue dañando al jugador", () =>
        {
            Lifecycle.Reset();
            var pgo = new GameObject("Player");
            var p = Add<PlayerHealth>(pgo);
            var col = pgo.AddComponent<Collider>();
            var projGo = new GameObject("Bullet");
            Invoke(Add<Projectile>(projGo), "OnTriggerEnter", col);
            return (p.CurrentHealth == 90 || p.CurrentHealth == 85) && projGo == null;
        });
        Check("proyectil ignora lo que no es IDamageable", () =>
        {
            Lifecycle.Reset();
            var wall = new GameObject("Wall");
            var col = wall.AddComponent<Collider>();
            var projGo = new GameObject("Bullet");
            Invoke(Add<Projectile>(projGo), "OnTriggerEnter", col);
            return projGo != null;
        });
    }

    // ------------------------------------------------------------------ T-104
    private static void T104()
    {
        List<GameObject> Alive() => UnityEngine.Object.FindObjectsOfType<Transform>()
            .Select(t => t.gameObject).Where(g => g.name == "Enemy(Clone)").ToList();

        PlayerHealth Setup()
        {
            Lifecycle.Reset();
            var player = Add<PlayerHealth>(new GameObject("Player"));
            var prefab = new GameObject("Enemy");
            prefab.SetActive(false); // los prefabs no "viven" en la escena
            Add<EnemySpawner>(new GameObject("Spawner"), prefab);
            Lifecycle.StartPending();
            return player;
        }

        void Run(float seconds) { int n = (int)Math.Round(seconds / 0.25f); for (int i = 0; i < n; i++) Lifecycle.Tick(0.25f); }

        Check("intervalo 1.75 s: nada a 1.5 s, uno a 1.75 s", () =>
        {
            Setup(); Run(1.5f); int a = Alive().Count; Run(0.25f); int b = Alive().Count;
            return a == 0 && b == 1;
        });
        Check("límite de 4 vivos (10 s)", () => { Setup(); Run(10f); return Alive().Count == 4; });
        Check("no supera el límite tras 30 s", () => { Setup(); Run(30f); return Alive().Count == 4; });
        Check("destruidos dejan de contar y se reponen", () =>
        {
            Setup(); Run(10f);
            var alive = Alive();
            UnityEngine.Object.Destroy(alive[0]); UnityEngine.Object.Destroy(alive[1]);
            int after = Alive().Count;
            Run(4f);
            return after == 2 && Alive().Count == 4;
        });
        Check("dos spawners llevan cuentas independientes (4 + 4)", () =>
        {
            Lifecycle.Reset();
            Add<PlayerHealth>(new GameObject("Player"));
            var prefab = new GameObject("Enemy");
            prefab.SetActive(false);
            Add<EnemySpawner>(new GameObject("SpawnerA"), prefab);
            Add<EnemySpawner>(new GameObject("SpawnerB"), prefab);
            Lifecycle.StartPending();
            Run(20f);
            return Alive().Count == 8;
        });
        Check("enemigos ajenos al spawner no cuentan para su límite", () =>
        {
            Setup();
            for (int i = 0; i < 3; i++) new GameObject("Enemy(Clone)");
            Run(12f);
            return Alive().Count == 3 + 4;
        });
        Check("no genera con el jugador muerto", () =>
        {
            var p = Setup(); Run(2f);
            p.TakeDamage(1000);
            foreach (var g in Alive()) UnityEngine.Object.Destroy(g);
            Run(6f);
            return Alive().Count == 0;
        });
    }

    public static int Main(string[] args)
    {
        string task = args.Length > 0 ? args[0] : "";
        try
        {
            switch (task)
            {
                case "T-101": T101(); break;
                case "T-102": T102(); break;
                case "T-103": T103(); break;
                case "T-104": T104(); break;
                default: Notes.Add("tarea desconocida " + task); break;
            }
        }
        catch (Exception e) { Notes.Add("fatal: " + e); }
        Console.WriteLine("@@RESULT@@" + JsonSerializer.Serialize(new { checks = Results, notes = Notes }));
        return 0;
    }
}
