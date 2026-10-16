#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BENCHMARK AGENTE — prueba el modelo cargado en LM Studio como agente de código:
Unity C#, Web TypeScript/HTML, C++, Unreal C++, Rust, .NET backend y JSON/Firebase.

- Si hay un modelo cargado lo usa directamente; si no, te deja elegir de la lista (y lo carga con su configuración).
- Usa TU configuración del modelo (no fija temperatura ni otros parámetros).
- 13 tareas reales (benchmark v4: 3 de Unity y 3 web), 1 intento cada una (--intentos para más): código con herramientas (leer, buscar, escribir,
  compilar) y 2 tareas MCP (Unity Editor y Blender simulados). Límite de 5 min por tarea; objetivo ≤ 3 min.
- El reporte incluye velocidad de lectura (prefill) y de generación.
- Las áreas cuyo compilador no esté instalado se omiten (N/A) y el script dice qué instalar.
- Califica solo: Unity con .NET (compila + tests de comportamiento); Web con Node.js si está instalado,
  si no, con análisis del código (calibrado contra los tests reales).
- Resultado: calificacion_agente_<modelo>_<fecha>.txt con notas de 1 a 10 por proceso y por tarea.

Uso:  python agente_benchmark.py              (modelo cargado)
      python agente_benchmark.py --modelo qwen3.8 --intentos 1
      python agente_benchmark.py --categorias cpp unreal rust dotnet firebase mcp
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_BASE = "http://localhost:1235"
# Candidatos de la ronda 3 (se buscan por nombre entre los modelos que tengas descargados)
MODEL_PATTERNS = [["qwen3.8-27b"], ["muse-glimmer"], ["gemma-4-26b-a4b-qat", "gemma-4-26b-a4b"], ["qwen3.6-35b-a3b"],
                  ["qwen3-coder-30b"]]
TASKS = ["T-101", "T-102", "T-103", "T-104", "W-201", "W-202", "W-203", "W-204"]
REQUEST_TIMEOUT = 900
MAX_STEPS = 30
TASK_WALL_SECONDS = 20 * 60

# -*- coding: utf-8 -*-
"""
Herramienta `build` de la ronda 3 (se usa igual para modelos locales y para Claude Haiku).

- Proyecto Unity (Assets/Scripts): compila de verdad con `dotnet build` contra stubs de la API de Unity
  si hay un SDK de .NET instalado; si no, usa un verificador estático (tipos del proyecto sin `using`,
  llaves desbalanceadas).
- Proyecto web (src/*.ts): verificador estático tipo "tsc-lite": imports relativos que no existen,
  nombres importados que el módulo no exporta, nombres de config usados sin importar, `import` fuera del
  nivel superior y llaves desbalanceadas.

Uso como script:  python buildcheck.py <carpeta_del_proyecto> [--no-dotnet]
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

UNITY_STUBS = "// Stubs mínimos de la API de Unity para compilar y ejecutar en .NET los scripts del benchmark.\n// Reproducen el comportamiento relevante: ciclo de vida (Awake/OnEnable/Start/Update/OnDisable),\n// \"fake null\" de objetos destruidos, búsqueda de componentes (incluye interfaces) y eventos.\n#pragma warning disable CS0660, CS0661, CS0618, CS0067, CS0414, CS0169, CS0649\nusing System;\nusing System.Collections;\nusing System.Collections.Generic;\nusing System.Linq;\nusing System.Reflection;\n\nnamespace UnityEngine\n{\n    [AttributeUsage(AttributeTargets.Field)] public class SerializeField : Attribute { }\n    [AttributeUsage(AttributeTargets.Field)] public class SerializeReference : Attribute { }\n    [AttributeUsage(AttributeTargets.Field)] public class HideInInspector : Attribute { }\n    [AttributeUsage(AttributeTargets.Field)] public class HeaderAttribute : Attribute { public HeaderAttribute(string h) { } }\n    [AttributeUsage(AttributeTargets.Field)] public class TooltipAttribute : Attribute { public TooltipAttribute(string t) { } }\n    [AttributeUsage(AttributeTargets.Field)] public class SpaceAttribute : Attribute { public SpaceAttribute() { } public SpaceAttribute(float h) { } }\n    [AttributeUsage(AttributeTargets.Field)] public class RangeAttribute : Attribute { public RangeAttribute(float a, float b) { } }\n    [AttributeUsage(AttributeTargets.Field)] public class MinAttribute : Attribute { public MinAttribute(float a) { } }\n    [AttributeUsage(AttributeTargets.Field)] public class TextAreaAttribute : Attribute { public TextAreaAttribute() { } public TextAreaAttribute(int a, int b) { } }\n    [AttributeUsage(AttributeTargets.Class, AllowMultiple = true)] public class RequireComponent : Attribute { public RequireComponent(Type a) { } public RequireComponent(Type a, Type b) { } }\n    [AttributeUsage(AttributeTargets.Class)] public class DisallowMultipleComponent : Attribute { }\n    [AttributeUsage(AttributeTargets.Class)] public class AddComponentMenu : Attribute { public AddComponentMenu(string m) { } public AddComponentMenu(string m, int o) { } }\n    [AttributeUsage(AttributeTargets.Class)] public class ExecuteAlways : Attribute { }\n    [AttributeUsage(AttributeTargets.Class)] public class ExecuteInEditMode : Attribute { }\n    [AttributeUsage(AttributeTargets.Class)] public class DefaultExecutionOrder : Attribute { public DefaultExecutionOrder(int o) { } }\n    [AttributeUsage(AttributeTargets.Class)] public class CreateAssetMenuAttribute : Attribute { public string fileName; public string menuName; public int order; }\n    [AttributeUsage(AttributeTargets.Method)] public class ContextMenu : Attribute { public ContextMenu(string n) { } }\n    [AttributeUsage(AttributeTargets.Method)] public class RuntimeInitializeOnLoadMethodAttribute : Attribute { public RuntimeInitializeOnLoadMethodAttribute() { } }\n\n    public enum FindObjectsSortMode { None, InstanceID }\n    public enum FindObjectsInactive { Exclude, Include }\n    public enum Space { World, Self }\n\n    public struct Vector3\n    {\n        public float x, y, z;\n        public Vector3(float x, float y, float z) { this.x = x; this.y = y; this.z = z; }\n        public Vector3(float x, float y) { this.x = x; this.y = y; z = 0; }\n        public static Vector3 zero => new Vector3(0, 0, 0);\n        public static Vector3 one => new Vector3(1, 1, 1);\n        public static Vector3 forward => new Vector3(0, 0, 1);\n        public static Vector3 back => new Vector3(0, 0, -1);\n        public static Vector3 up => new Vector3(0, 1, 0);\n        public static Vector3 down => new Vector3(0, -1, 0);\n        public static Vector3 right => new Vector3(1, 0, 0);\n        public static Vector3 left => new Vector3(-1, 0, 0);\n        public float magnitude => (float)Math.Sqrt(x * x + y * y + z * z);\n        public float sqrMagnitude => x * x + y * y + z * z;\n        public Vector3 normalized { get { var m = magnitude; return m > 1e-5f ? this / m : zero; } }\n        public static Vector3 operator +(Vector3 a, Vector3 b) => new Vector3(a.x + b.x, a.y + b.y, a.z + b.z);\n        public static Vector3 operator -(Vector3 a, Vector3 b) => new Vector3(a.x - b.x, a.y - b.y, a.z - b.z);\n        public static Vector3 operator -(Vector3 a) => new Vector3(-a.x, -a.y, -a.z);\n        public static Vector3 operator *(Vector3 a, float d) => new Vector3(a.x * d, a.y * d, a.z * d);\n        public static Vector3 operator *(float d, Vector3 a) => new Vector3(a.x * d, a.y * d, a.z * d);\n        public static Vector3 operator /(Vector3 a, float d) => new Vector3(a.x / d, a.y / d, a.z / d);\n        public static bool operator ==(Vector3 a, Vector3 b) => (a - b).sqrMagnitude < 1e-10f;\n        public static bool operator !=(Vector3 a, Vector3 b) => !(a == b);\n        public static float Distance(Vector3 a, Vector3 b) => (a - b).magnitude;\n        public static Vector3 Lerp(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t);\n        public static Vector3 MoveTowards(Vector3 c, Vector3 t, float d) { var v = t - c; var m = v.magnitude; return m <= d || m == 0 ? t : c + v / m * d; }\n        public static float Dot(Vector3 a, Vector3 b) => a.x * b.x + a.y * b.y + a.z * b.z;\n        public override string ToString() => $\"({x}, {y}, {z})\";\n    }\n\n    public struct Vector2\n    {\n        public float x, y;\n        public Vector2(float x, float y) { this.x = x; this.y = y; }\n        public static Vector2 zero => new Vector2(0, 0);\n        public static Vector2 one => new Vector2(1, 1);\n        public float magnitude => (float)Math.Sqrt(x * x + y * y);\n        public static Vector2 operator +(Vector2 a, Vector2 b) => new Vector2(a.x + b.x, a.y + b.y);\n        public static Vector2 operator -(Vector2 a, Vector2 b) => new Vector2(a.x - b.x, a.y - b.y);\n        public static Vector2 operator *(Vector2 a, float d) => new Vector2(a.x * d, a.y * d);\n        public static implicit operator Vector3(Vector2 v) => new Vector3(v.x, v.y, 0);\n        public static implicit operator Vector2(Vector3 v) => new Vector2(v.x, v.y);\n    }\n\n    public struct Quaternion\n    {\n        public float x, y, z, w;\n        public static Quaternion identity => new Quaternion { w = 1 };\n        public static Quaternion Euler(float x, float y, float z) => identity;\n        public static Quaternion Euler(Vector3 e) => identity;\n        public static Quaternion LookRotation(Vector3 f) => identity;\n        public static Quaternion LookRotation(Vector3 f, Vector3 u) => identity;\n        public static Vector3 operator *(Quaternion q, Vector3 v) => v;\n        public static Quaternion operator *(Quaternion a, Quaternion b) => a;\n    }\n\n    public struct Color\n    {\n        public float r, g, b, a;\n        public Color(float r, float g, float b, float a = 1f) { this.r = r; this.g = g; this.b = b; this.a = a; }\n        public static Color white => new Color(1, 1, 1);\n        public static Color black => new Color(0, 0, 0);\n        public static Color red => new Color(1, 0, 0);\n        public static Color green => new Color(0, 1, 0);\n        public static Color yellow => new Color(1, 0.92f, 0.016f);\n        public static Color clear => new Color(0, 0, 0, 0);\n        public static Color Lerp(Color x, Color y, float t) { t = Mathf.Clamp01(t); return new Color(x.r + (y.r - x.r) * t, x.g + (y.g - x.g) * t, x.b + (y.b - x.b) * t, x.a + (y.a - x.a) * t); }\n    }\n\n    public static class Mathf\n    {\n        public const float PI = (float)Math.PI;\n        public const float Infinity = float.PositiveInfinity;\n        public const float NegativeInfinity = float.NegativeInfinity;\n        public const float Epsilon = float.Epsilon;\n        public const float Deg2Rad = PI / 180f;\n        public const float Rad2Deg = 180f / PI;\n        public static int Min(int a, int b) => Math.Min(a, b);\n        public static float Min(float a, float b) => Math.Min(a, b);\n        public static int Min(params int[] v) => v.Min();\n        public static float Min(params float[] v) => v.Min();\n        public static int Max(int a, int b) => Math.Max(a, b);\n        public static float Max(float a, float b) => Math.Max(a, b);\n        public static int Max(params int[] v) => v.Max();\n        public static float Max(params float[] v) => v.Max();\n        public static int Clamp(int v, int a, int b) => v < a ? a : (v > b ? b : v);\n        public static float Clamp(float v, float a, float b) => v < a ? a : (v > b ? b : v);\n        public static float Clamp01(float v) => Clamp(v, 0f, 1f);\n        public static int Abs(int v) => Math.Abs(v);\n        public static float Abs(float v) => Math.Abs(v);\n        public static float Sign(float v) => v >= 0 ? 1f : -1f;\n        public static float Sqrt(float v) => (float)Math.Sqrt(v);\n        public static float Pow(float a, float b) => (float)Math.Pow(a, b);\n        public static float Sin(float v) => (float)Math.Sin(v);\n        public static float Cos(float v) => (float)Math.Cos(v);\n        public static bool Approximately(float a, float b) => Math.Abs(a - b) < Math.Max(1e-6f * Math.Max(Math.Abs(a), Math.Abs(b)), 1e-6f);\n        public static int RoundToInt(float v) => (int)Math.Round(v, MidpointRounding.ToEven);\n        public static int FloorToInt(float v) => (int)Math.Floor(v);\n        public static int CeilToInt(float v) => (int)Math.Ceiling(v);\n        public static float Round(float v) => (float)Math.Round(v);\n        public static float Floor(float v) => (float)Math.Floor(v);\n        public static float Ceil(float v) => (float)Math.Ceiling(v);\n        public static float Lerp(float a, float b, float t) => a + (b - a) * Clamp01(t);\n        public static float LerpUnclamped(float a, float b, float t) => a + (b - a) * t;\n        public static float InverseLerp(float a, float b, float v) => a == b ? 0f : Clamp01((v - a) / (b - a));\n        public static float MoveTowards(float c, float t, float d) => Math.Abs(t - c) <= d ? t : c + Math.Sign(t - c) * d;\n        public static float Repeat(float t, float l) => Clamp(t - (float)Math.Floor(t / l) * l, 0f, l);\n        public static float PingPong(float t, float l) { t = Repeat(t, l * 2f); return l - Math.Abs(t - l); }\n        public static float SmoothStep(float a, float b, float t) { t = Clamp01(t); t = t * t * (3f - 2f * t); return a + (b - a) * t; }\n    }\n\n    public static class Time\n    {\n        public static float deltaTime = 0.02f;\n        public static float time = 0f;\n        public static float fixedDeltaTime = 0.02f;\n        public static float unscaledDeltaTime => deltaTime;\n        public static float unscaledTime => time;\n        public static float timeScale = 1f;\n        public static int frameCount = 0;\n        public static float timeSinceLevelLoad => time;\n    }\n\n    public static class Random\n    {\n        private static readonly System.Random _r = new System.Random(1234);\n        public static int Range(int a, int b) => _r.Next(a, b);\n        public static float Range(float a, float b) => a + (float)_r.NextDouble() * (b - a);\n        public static float value => (float)_r.NextDouble();\n    }\n\n    public static class Application\n    {\n        public static bool isPlaying = true;\n        public static bool isEditor = false;\n        public static int targetFrameRate = 60;\n    }\n\n    public static class Debug\n    {\n        public static int LogCount;\n        public static void Log(object m) { LogCount++; }\n        public static void Log(object m, Object ctx) { LogCount++; }\n        public static void LogWarning(object m) { LogCount++; }\n        public static void LogWarning(object m, Object ctx) { LogCount++; }\n        public static void LogError(object m) { LogCount++; }\n        public static void LogError(object m, Object ctx) { LogCount++; }\n        public static void LogException(Exception e) { LogCount++; }\n        public static void LogFormat(string f, params object[] a) { LogCount++; }\n        public static void Assert(bool c) { }\n        public static void Assert(bool c, object m) { }\n        public static void DrawLine(Vector3 a, Vector3 b) { }\n        public static void DrawRay(Vector3 a, Vector3 b) { }\n    }\n\n    public class YieldInstruction { }\n    public class Coroutine : YieldInstruction { }\n    public class WaitForSeconds : YieldInstruction { public WaitForSeconds(float s) { } }\n    public class WaitForEndOfFrame : YieldInstruction { }\n    public class WaitForFixedUpdate : YieldInstruction { }\n\n    public class Object\n    {\n        internal static readonly List<Object> Live = new List<Object>();\n        internal bool _destroyed;\n        private static int _nextId = 1;\n        private readonly int _id;\n        public string name { get; set; } = \"\";\n\n        public Object() { _id = _nextId++; Live.Add(this); }\n        public int GetInstanceID() => _id;\n\n        public static bool operator ==(Object a, Object b)\n        {\n            bool aNull = ReferenceEquals(a, null) || a._destroyed;\n            bool bNull = ReferenceEquals(b, null) || b._destroyed;\n            if (aNull && bNull) return true;\n            if (aNull || bNull) return false;\n            return ReferenceEquals(a, b);\n        }\n        public static bool operator !=(Object a, Object b) => !(a == b);\n        public static implicit operator bool(Object o) => !ReferenceEquals(o, null) && !o._destroyed;\n        public override bool Equals(object other) => other is Object o ? this == o : (other == null && _destroyed);\n        public override int GetHashCode() => _id;\n        public override string ToString() => name;\n\n        public static void Destroy(Object obj) { if (!ReferenceEquals(obj, null)) obj.DestroyInternal(); }\n        public static void Destroy(Object obj, float t) => Destroy(obj);\n        public static void DestroyImmediate(Object obj) => Destroy(obj);\n        public static void DontDestroyOnLoad(Object obj) { }\n\n        internal virtual void DestroyInternal()\n        {\n            if (_destroyed) return;\n            _destroyed = true;\n            Live.Remove(this);\n        }\n\n        public static GameObject Instantiate(GameObject original) => GameObject.CloneOf(original);\n        public static GameObject Instantiate(GameObject original, Vector3 pos, Quaternion rot) { var g = GameObject.CloneOf(original); g.transform.position = pos; return g; }\n        public static GameObject Instantiate(GameObject original, Vector3 pos, Quaternion rot, Transform parent) => Instantiate(original, pos, rot);\n        public static GameObject Instantiate(GameObject original, Transform parent) => GameObject.CloneOf(original);\n        public static T Instantiate<T>(T original) where T : Object\n        {\n            if (original is GameObject g) return (T)(Object)GameObject.CloneOf(g);\n            if (original is Component c) { var go = GameObject.CloneOf(c.gameObject); return (T)(Object)go.GetComponent(c.GetType()); }\n            throw new NotSupportedException();\n        }\n        public static T Instantiate<T>(T original, Vector3 pos, Quaternion rot) where T : Object\n        {\n            var r = Instantiate(original);\n            if (r is GameObject g) g.transform.position = pos; else if (r is Component c) c.transform.position = pos;\n            return r;\n        }\n        public static T Instantiate<T>(T original, Transform parent) where T : Object => Instantiate(original);\n        public static T Instantiate<T>(T original, Vector3 pos, Quaternion rot, Transform parent) where T : Object => Instantiate(original, pos, rot);\n\n        private static IEnumerable<T> AllLive<T>() where T : class =>\n            Live.ToList().OfType<Component>().Where(c => !c._destroyed && c.gameObject.activeInHierarchy).OfType<T>();\n\n        public static T FindObjectOfType<T>() where T : Object => AllLive<T>().FirstOrDefault();\n        public static T FindObjectOfType<T>(bool includeInactive) where T : Object => AllLive<T>().FirstOrDefault();\n        public static T FindFirstObjectByType<T>() where T : Object => AllLive<T>().FirstOrDefault();\n        public static T FindFirstObjectByType<T>(FindObjectsInactive i) where T : Object => AllLive<T>().FirstOrDefault();\n        public static T FindAnyObjectByType<T>() where T : Object => AllLive<T>().FirstOrDefault();\n        public static T FindAnyObjectByType<T>(FindObjectsInactive i) where T : Object => AllLive<T>().FirstOrDefault();\n        public static T[] FindObjectsOfType<T>() where T : Object => AllLive<T>().ToArray();\n        public static T[] FindObjectsByType<T>(FindObjectsSortMode m) where T : Object => AllLive<T>().ToArray();\n        public static T[] FindObjectsByType<T>(FindObjectsInactive i, FindObjectsSortMode m) where T : Object => AllLive<T>().ToArray();\n    }\n\n    public class GameObject : Object\n    {\n        internal readonly List<Component> _components = new List<Component>();\n        private bool _active = true;\n        public string tag { get; set; } = \"Untagged\";\n        public int layer { get; set; }\n        public Transform transform { get; }\n        public GameObject gameObject => this;\n\n        public GameObject() : this(\"GameObject\") { }\n        public GameObject(string name) { this.name = name; transform = new Transform(); transform.Attach(this); _components.Add(transform); }\n        public GameObject(string name, params Type[] comps) : this(name) { foreach (var t in comps) AddComponent(t); }\n\n        internal static GameObject CloneOf(GameObject g)\n        {\n            var clone = new GameObject(g.name + \"(Clone)\");\n            foreach (var c in g._components)\n                if (!(c is Transform)) clone.AddComponent(c.GetType());\n            return clone;\n        }\n\n        public bool activeSelf => _active;\n        public bool activeInHierarchy => _active && !_destroyed;\n        public void SetActive(bool v)\n        {\n            if (_active == v) return;\n            _active = v;\n            foreach (var c in _components.ToList())\n                if (c is Behaviour b && b.enabled) Lifecycle.Invoke(b, v ? \"OnEnable\" : \"OnDisable\");\n        }\n        public bool CompareTag(string t) => tag == t;\n\n        public T AddComponent<T>() where T : Component => (T)AddComponent(typeof(T));\n        public Component AddComponent(Type t) => AddComponentWith(t, null);\n\n        /// Agrega un componente permitiendo \"deserializar\" campos antes de Awake (como el Inspector).\n        public Component AddComponentWith(Type t, Action<Component> beforeAwake)\n        {\n            var c = (Component)Activator.CreateInstance(t, true);\n            c.Attach(this);\n            _components.Add(c);\n            beforeAwake?.Invoke(c);\n            if (c is MonoBehaviour mb && activeInHierarchy)\n            {\n                Lifecycle.Invoke(mb, \"Awake\");\n                if (mb.enabled && !mb._destroyed) Lifecycle.Invoke(mb, \"OnEnable\");\n            }\n            return c;\n        }\n\n        public Component GetComponent(Type t) => _components.FirstOrDefault(c => !c._destroyed && t.IsInstanceOfType(c));\n        public T GetComponent<T>() { foreach (var c in _components) if (!c._destroyed && c is T x) return x; return default; }\n        public bool TryGetComponent<T>(out T component) { component = GetComponent<T>(); return component != null; }\n        public bool TryGetComponent(Type t, out Component component) { component = GetComponent(t); return component != null; }\n        public T[] GetComponents<T>() => _components.Where(c => !c._destroyed).OfType<T>().ToArray();\n        public T GetComponentInChildren<T>() => GetComponent<T>();\n        public T GetComponentInChildren<T>(bool inactive) => GetComponent<T>();\n        public T GetComponentInParent<T>() => GetComponent<T>();\n        public T[] GetComponentsInChildren<T>() => GetComponents<T>();\n\n        public static GameObject Find(string n) => Live.OfType<GameObject>().FirstOrDefault(g => g.name == n && g.activeInHierarchy);\n        public static GameObject FindWithTag(string t) => Live.OfType<GameObject>().FirstOrDefault(g => g.tag == t && g.activeInHierarchy);\n        public static GameObject[] FindGameObjectsWithTag(string t) => Live.OfType<GameObject>().Where(g => g.tag == t && g.activeInHierarchy).ToArray();\n\n        internal override void DestroyInternal()\n        {\n            if (_destroyed) return;\n            foreach (var c in _components.ToList())\n            {\n                if (c is Behaviour b && b.enabled && activeInHierarchy) Lifecycle.Invoke(b, \"OnDisable\");\n                if (c is MonoBehaviour) Lifecycle.Invoke(c, \"OnDestroy\");\n                c.MarkDestroyed();\n            }\n            base.DestroyInternal();\n        }\n    }\n\n    public class Component : Object\n    {\n        private GameObject _go;\n        internal void Attach(GameObject g) { _go = g; name = g.name; }\n        internal void MarkDestroyed() { _destroyed = true; Live.Remove(this); }\n        public GameObject gameObject => _go;\n        public Transform transform => _go.transform;\n        public string tag { get => _go.tag; set => _go.tag = value; }\n        public bool CompareTag(string t) => _go.CompareTag(t);\n        public Component GetComponent(Type t) => _go.GetComponent(t);\n        public T GetComponent<T>() => _go.GetComponent<T>();\n        public bool TryGetComponent<T>(out T component) => _go.TryGetComponent(out component);\n        public bool TryGetComponent(Type t, out Component component) => _go.TryGetComponent(t, out component);\n        public T[] GetComponents<T>() => _go.GetComponents<T>();\n        public T GetComponentInChildren<T>() => _go.GetComponentInChildren<T>();\n        public T GetComponentInChildren<T>(bool inactive) => _go.GetComponentInChildren<T>();\n        public T GetComponentInParent<T>() => _go.GetComponentInParent<T>();\n        public T[] GetComponentsInChildren<T>() => _go.GetComponentsInChildren<T>();\n\n        internal override void DestroyInternal()\n        {\n            if (_destroyed) return;\n            if (this is Behaviour b && b.enabled && _go.activeInHierarchy) Lifecycle.Invoke(b, \"OnDisable\");\n            if (this is MonoBehaviour) Lifecycle.Invoke(this, \"OnDestroy\");\n            _go._components.Remove(this);\n            base.DestroyInternal();\n        }\n    }\n\n    public class Transform : Component, IEnumerable\n    {\n        public Vector3 position { get; set; }\n        public Vector3 localPosition { get => position; set => position = value; }\n        public Quaternion rotation { get; set; } = Quaternion.identity;\n        public Quaternion localRotation { get => rotation; set => rotation = value; }\n        public Vector3 eulerAngles { get; set; }\n        public Vector3 localScale { get; set; } = Vector3.one;\n        public Vector3 forward => Vector3.forward;\n        public Vector3 right => Vector3.right;\n        public Vector3 up => Vector3.up;\n        public Transform parent { get; set; }\n        public int childCount => 0;\n        public void SetParent(Transform p) { parent = p; }\n        public void SetParent(Transform p, bool w) { parent = p; }\n        public void Translate(Vector3 d) { position += d; }\n        public void Translate(Vector3 d, Space s) { position += d; }\n        public void Rotate(Vector3 e) { }\n        public void Rotate(float x, float y, float z) { }\n        public void LookAt(Transform t) { }\n        public void LookAt(Vector3 p) { }\n        public Transform GetChild(int i) => null;\n        public IEnumerator GetEnumerator() { yield break; }\n    }\n\n    public class Behaviour : Component\n    {\n        private bool _enabled = true;\n        internal bool _started;\n        public bool enabled\n        {\n            get => _enabled;\n            set\n            {\n                if (_enabled == value) return;\n                _enabled = value;\n                if (gameObject != null && gameObject.activeInHierarchy && !_destroyed)\n                    Lifecycle.Invoke(this, value ? \"OnEnable\" : \"OnDisable\");\n            }\n        }\n        public bool isActiveAndEnabled => _enabled && gameObject.activeInHierarchy;\n    }\n\n    public class MonoBehaviour : Behaviour\n    {\n        public Coroutine StartCoroutine(IEnumerator r) => new Coroutine();\n        public Coroutine StartCoroutine(string n) => new Coroutine();\n        public void StopCoroutine(Coroutine c) { }\n        public void StopCoroutine(IEnumerator c) { }\n        public void StopAllCoroutines() { }\n        public void Invoke(string m, float t) { }\n        public void InvokeRepeating(string m, float t, float r) { }\n        public void CancelInvoke() { }\n        public void CancelInvoke(string m) { }\n        public static void print(object m) { Debug.Log(m); }\n    }\n\n    public class ScriptableObject : Object\n    {\n        public static T CreateInstance<T>() where T : ScriptableObject => (T)Activator.CreateInstance(typeof(T), true);\n        public static ScriptableObject CreateInstance(Type t) => (ScriptableObject)Activator.CreateInstance(t, true);\n    }\n\n    public class Collider : Component { public bool isTrigger { get; set; } public bool enabled { get; set; } = true; }\n    public class BoxCollider : Collider { }\n    public class SphereCollider : Collider { }\n    public class CapsuleCollider : Collider { }\n    public class Collider2D : Component { public bool isTrigger { get; set; } }\n    public class Rigidbody : Component { public Vector3 velocity { get; set; } public Vector3 linearVelocity { get; set; } public bool isKinematic { get; set; } public void AddForce(Vector3 f) { } }\n    public class Rigidbody2D : Component { public Vector2 velocity { get; set; } public Vector2 linearVelocity { get; set; } }\n    public class Collision { public Collider collider; public GameObject gameObject => collider?.gameObject; public Transform transform => collider?.transform; }\n    public class Collision2D { public Collider2D collider; public GameObject gameObject => collider?.gameObject; }\n    public class Renderer : Component { public bool enabled { get; set; } = true; }\n    public class Animator : Behaviour { public void SetTrigger(string n) { } public void SetBool(string n, bool v) { } public void SetFloat(string n, float v) { } public void SetInteger(string n, int v) { } }\n    public class AudioSource : Behaviour { public void Play() { } public void PlayOneShot(object c) { } public void Stop() { } }\n    public class Canvas : Behaviour { }\n    public class RectTransform : Transform { public Vector2 sizeDelta { get; set; } public Vector2 anchoredPosition { get; set; } }\n\n    /// Invocación de métodos de ciclo de vida por reflexión (privados o públicos).\n    public static class Lifecycle\n    {\n        public static void Invoke(object target, string method)\n        {\n            var t = target.GetType();\n            while (t != null && t != typeof(MonoBehaviour))\n            {\n                var m = t.GetMethod(method, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly, null, Type.EmptyTypes, null);\n                if (m != null)\n                {\n                    var r = m.Invoke(target, null);\n                    if (r is IEnumerator e) { while (e.MoveNext()) { } }\n                    return;\n                }\n                t = t.BaseType;\n            }\n        }\n\n        public static List<MonoBehaviour> Active() =>\n            Object.Live.ToList().OfType<MonoBehaviour>().Where(b => !b._destroyed && b.enabled && b.gameObject.activeInHierarchy).ToList();\n\n        public static void StartPending()\n        {\n            foreach (var b in Active())\n                if (!b._started) { b._started = true; Invoke(b, \"Start\"); }\n        }\n\n        public static void Tick(float dt)\n        {\n            Time.deltaTime = dt;\n            Time.time += dt;\n            Time.frameCount++;\n            StartPending();\n            foreach (var b in Active()) if (!b._destroyed && b.enabled) Invoke(b, \"Update\");\n            foreach (var b in Active()) if (!b._destroyed && b.enabled) Invoke(b, \"LateUpdate\");\n        }\n\n        public static void Reset()\n        {\n            foreach (var o in Object.Live.ToList()) o._destroyed = true;\n            Object.Live.Clear();\n            Time.time = 0; Time.deltaTime = 0.02f; Time.frameCount = 0;\n            Debug.LogCount = 0;\n        }\n    }\n}\n\nnamespace UnityEngine.Events\n{\n    public delegate void UnityAction();\n    public delegate void UnityAction<T0>(T0 a);\n    public delegate void UnityAction<T0, T1>(T0 a, T1 b);\n    public class UnityEvent\n    {\n        private readonly List<UnityAction> _l = new List<UnityAction>();\n        public void AddListener(UnityAction a) => _l.Add(a);\n        public void RemoveListener(UnityAction a) => _l.Remove(a);\n        public void RemoveAllListeners() => _l.Clear();\n        public void Invoke() { foreach (var a in _l.ToList()) a(); }\n    }\n    public class UnityEvent<T0>\n    {\n        private readonly List<UnityAction<T0>> _l = new List<UnityAction<T0>>();\n        public void AddListener(UnityAction<T0> a) => _l.Add(a);\n        public void RemoveListener(UnityAction<T0> a) => _l.Remove(a);\n        public void RemoveAllListeners() => _l.Clear();\n        public void Invoke(T0 v) { foreach (var a in _l.ToList()) a(v); }\n    }\n    public class UnityEvent<T0, T1>\n    {\n        private readonly List<UnityAction<T0, T1>> _l = new List<UnityAction<T0, T1>>();\n        public void AddListener(UnityAction<T0, T1> a) => _l.Add(a);\n        public void RemoveListener(UnityAction<T0, T1> a) => _l.Remove(a);\n        public void RemoveAllListeners() => _l.Clear();\n        public void Invoke(T0 v, T1 w) { foreach (var a in _l.ToList()) a(v, w); }\n    }\n}\n\nnamespace UnityEngine.UI\n{\n    public class Graphic : Behaviour { public Color color { get; set; } = Color.white; public bool raycastTarget { get; set; } }\n    public class MaskableGraphic : Graphic { }\n    public class Image : MaskableGraphic\n    {\n        public enum Type { Simple, Sliced, Tiled, Filled }\n        public enum FillMethod { Horizontal, Vertical, Radial90, Radial180, Radial360 }\n        private float _fill = 1f;\n        public float fillAmount { get => _fill; set => _fill = Mathf.Clamp01(value); }\n        public Type type { get; set; }\n        public FillMethod fillMethod { get; set; }\n        public object sprite { get; set; }\n    }\n    public class Text : MaskableGraphic { public string text { get; set; } = \"\"; }\n    public class Slider : Behaviour\n    {\n        private float _v;\n        public float minValue { get; set; } = 0f;\n        public float maxValue { get; set; } = 1f;\n        public bool wholeNumbers { get; set; }\n        public float value { get => _v; set => _v = Mathf.Clamp(value, minValue, maxValue); }\n        public float normalizedValue { get => Mathf.InverseLerp(minValue, maxValue, _v); set => value = Mathf.Lerp(minValue, maxValue, value); }\n        public void SetValueWithoutNotify(float v) => value = v;\n    }\n}\n\nnamespace TMPro\n{\n    public class TMP_Text : UnityEngine.UI.MaskableGraphic { public string text { get; set; } = \"\"; public void SetText(string t) { text = t; } public void SetText(string f, float a) { text = f; } }\n    public class TextMeshProUGUI : TMP_Text { }\n    public class TextMeshPro : TMP_Text { }\n}\n"
_DOTNET_CACHE = {}


def _strip(src):
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r'@"(?:[^"]|"")*"', '""', src)
    src = re.sub(r'\$?"(?:\\.|[^"\\\n])*"', '""', src)
    src = re.sub(r"`(?:\\.|[^`\\])*`", "``", src, flags=re.S)
    src = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", src)
    return src


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _balance(path, code):
    errs = []
    for o, c, name in (("{", "}", "llaves"), ("(", ")", "paréntesis")):
        if code.count(o) != code.count(c):
            errs.append(f"{path}: error: {name} desbalanceadas ({code.count(o)} '{o}' vs {code.count(c)} '{c}')")
    return errs


# ----------------------------------------------------------------------------- C#
def _dotnet_sdk():
    if "sdk" in _DOTNET_CACHE:
        return _DOTNET_CACHE["sdk"]
    exe = shutil.which("dotnet")
    sdk = None
    if exe:
        try:
            out = subprocess.run([exe, "--list-sdks"], capture_output=True, text=True, timeout=30).stdout
            majors = sorted({int(m) for m in re.findall(r"^(\d+)\.\d+\.\d+", out, re.M) if int(m) >= 6})
            if majors:
                sdk = (exe, majors[-1])
        except Exception:
            sdk = None
    _DOTNET_CACHE["sdk"] = sdk
    return sdk


def _cs_dotnet(root, sdk):
    exe, major = sdk
    import hashlib
    work = Path(tempfile.gettempdir()) / ("bench_r3_dotnet_" + hashlib.md5(str(root.resolve()).encode()).hexdigest()[:10])
    src_dir = work / "src"
    if src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True)
    for p in (root / "Assets" / "Scripts").rglob("*.cs"):
        t = src_dir / p.relative_to(root / "Assets" / "Scripts")
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, t)
    (work / "UnityStubs.cs").write_text(UNITY_STUBS or "", encoding="utf-8")
    (work / "nuget.config").write_text(
        '<?xml version="1.0" encoding="utf-8"?><configuration><packageSources><clear /></packageSources></configuration>',
        encoding="utf-8")
    (work / "Check.csproj").write_text(f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Library</OutputType><TargetFramework>net{major}.0</TargetFramework>
    <ImplicitUsings>disable</ImplicitUsings><Nullable>disable</Nullable><LangVersion>latest</LangVersion>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <NoWarn>CS0618;CS0414;CS0169;CS0649;CS0067;CS8632;CS0108;CS0114</NoWarn>
  </PropertyGroup>
  <ItemGroup><Compile Include="src/**/*.cs" /><Compile Include="UnityStubs.cs" /></ItemGroup>
</Project>""", encoding="utf-8")
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    try:
        r = subprocess.run([exe, "build", "-nologo", "-v", "q", "-clp:NoSummary"], cwd=work, capture_output=True,
                           text=True, timeout=180, env=env)
    except subprocess.TimeoutExpired:
        return None
    lines = (r.stdout + r.stderr).splitlines()
    errs = []
    for l in lines:
        if ": error " in l:
            l = re.sub(r"\s*\[.*?\.csproj\]\s*$", "", l)
            l = l.replace(str(src_dir) + os.sep, "Assets/Scripts/").replace(str(src_dir) + "/", "Assets/Scripts/")
            l = re.sub(r"^.*?(Assets[/\\]Scripts[/\\])", r"\1", l).replace("\\", "/")
            if "UnityStubs.cs" in l or "NETSDK" in l or "NU1" in l:
                if "UnityStubs.cs" in l:
                    continue
                return None  # problema del SDK, no del código: usar verificador estático
            errs.append(l.strip())
    if r.returncode != 0 and not errs:
        return None
    return sorted(set(errs))


def _cs_static(root):
    files = {p: p.read_text(encoding="utf-8", errors="replace") for p in (root / "Assets" / "Scripts").rglob("*.cs")}
    types = {}
    for p, s in files.items():
        code = _strip(s)
        ns = re.search(r"\bnamespace\s+([\w.]+)", code)
        for t in re.findall(r"\b(?:class|interface|struct|enum)\s+([A-Z]\w*)", code):
            types.setdefault(t, set()).add(ns.group(1) if ns else "")
    errs = []
    for p, s in files.items():
        rel = str(p.relative_to(root)).replace("\\", "/")
        code = _strip(s)
        errs += _balance(rel, code)
        ns = re.search(r"\bnamespace\s+([\w.]+)", code)
        own = ns.group(1) if ns else ""
        usings = set(re.findall(r"^\s*using\s+([\w.]+)\s*;", code, re.M))
        visible = {own} | usings | {".".join(own.split(".")[:i]) for i in range(1, len(own.split(".")))}
        declared_here = set(re.findall(r"\b(?:class|interface|struct|enum)\s+([A-Z]\w*)", code))
        for t, nss in types.items():
            if t in declared_here:
                continue
            for m in re.finditer(r"(?<![\w.])" + re.escape(t) + r"\b", code):
                if nss & visible or "" in nss:
                    break
                line = code[:m.start()].count("\n") + 1
                errs.append(f"{rel}({line}): error CS0246: The type or namespace name '{t}' could not be found "
                            f"(are you missing a using directive? It is declared in: {', '.join(sorted(nss))})")
                break
    return errs


# ----------------------------------------------------------------------------- TypeScript
def _ts_exports(src):
    code = _strip(src)
    names = set(re.findall(r"\bexport\s+(?:declare\s+)?(?:async\s+)?(?:const|let|function|interface|type|class|enum)\s+([A-Za-z_$][\w$]*)", code))
    for grp in re.findall(r"\bexport\s*\{([^}]*)\}", code):
        for part in grp.split(","):
            part = part.strip()
            if part:
                names.add(part.split(" as ")[-1].strip())
    return names


def _ts_resolve(from_file, spec, root):
    base = (from_file.parent / spec).resolve()
    cands = [base, base.with_suffix(".ts"), Path(str(base) + ".ts"), base / "index.ts"]
    if base.suffix == ".js":
        cands.insert(0, base.with_suffix(".ts"))
    for c in cands:
        if c.is_file() and str(c).startswith(str(root.resolve())):
            return c
    return None


def _ts_static(root):
    files = {p: p.read_text(encoding="utf-8", errors="replace") for p in (root / "src").rglob("*.ts")}
    exports = {p.resolve(): _ts_exports(s) for p, s in files.items()}
    known = {}
    for p, names in exports.items():
        if "config" in p.parts:
            for n in names:
                known[n] = p
    errs = []
    for p, s in files.items():
        rel = str(p.relative_to(root)).replace("\\", "/")
        code = _strip(s)
        errs += _balance(rel, code)
        imported = set()
        seen_code = False
        for i, line in enumerate(code.splitlines(), 1):
            st = line.strip()
            if not st:
                continue
            if st.startswith("import "):
                if seen_code:
                    errs.append(f"{rel}({i}): error TS1232: An import declaration can only be used at the top level of a module (move imports to the top)")
            elif not st.startswith(("*", "/**", "*/", "export type", "}")):
                seen_code = True
        icode = _strip_comments(s)
        for m in re.finditer(r"import\s+(type\s+)?(?:\{([^}]*)\}|(\w+)|\*\s+as\s+(\w+))\s+from\s+[\"']([^\"']+)[\"']", icode):
            spec = m.group(5)
            line = icode[:m.start()].count("\n") + 1
            names = [x.strip().split(" as ")[0].replace("type ", "").strip() for x in (m.group(2) or "").split(",") if x.strip()]
            locals_ = [x.strip().split(" as ")[-1].replace("type ", "").strip() for x in (m.group(2) or "").split(",") if x.strip()]
            imported |= set(locals_) | ({m.group(3)} if m.group(3) else set()) | ({m.group(4)} if m.group(4) else set())
            if not spec.startswith("."):
                continue
            target = _ts_resolve(p, spec, root)
            if target is None:
                errs.append(f"{rel}({line}): error TS2307: Cannot find module '{spec}' or its corresponding type declarations.")
                continue
            if m.group(3):
                errs.append(f"{rel}({line}): error TS1192: Module '{spec}' has no default export.")
            for n in names:
                if n and n not in exports.get(target.resolve(), set()):
                    errs.append(f"{rel}({line}): error TS2305: Module '{spec}' has no exported member '{n}'.")
        declared = set(re.findall(r"\b(?:const|let|var|function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)", code))
        for n, src_file in known.items():
            if src_file == p.resolve() or n in imported or n in declared:
                continue
            mm = re.search(r"(?<![\w.$])" + re.escape(n) + r"\b", code)
            if mm:
                line = code[:mm.start()].count("\n") + 1
                errs.append(f"{rel}({line}): error TS2304: Cannot find name '{n}' (it is exported by "
                            f"{str(src_file.relative_to(root.resolve())).replace(chr(92), '/')}; import it).")
    return errs


# ----------------------------------------------------------------------------- API
def run_build(root, allow_dotnet=True):
    root = Path(root)
    if (root / "Assets" / "Scripts").exists():
        sdk = _dotnet_sdk() if allow_dotnet else None
        if sdk:
            errs = _cs_dotnet(root, sdk)
            if errs is not None:
                tool = f"dotnet (net{sdk[1]}.0) + stubs de Unity"
                return (f"Build OK ({tool}): 0 errores." if not errs else
                        f"Build FALLÓ ({tool}): {len(errs)} error(es)\n" + "\n".join(errs[:25]))
        errs = _cs_static(root)
        tool = "verificador estático C#"
    elif (root / "src").exists():
        errs = _ts_static(root)
        tool = "verificador estático TypeScript"
    else:
        return "ERROR: no reconozco el tipo de proyecto"
    return (f"Build OK ({tool}): 0 errores." if not errs else
            f"Build FALLÓ ({tool}): {len(errs)} error(es)\n" + "\n".join(errs[:25]))


def build_mode():
    sdk = _dotnet_sdk()
    return f"C#: dotnet net{sdk[1]}.0" if sdk else "C#: verificador estático (no encontré SDK de .NET)"



PROJECTS = {"unity": {"Assets/Scripts/Combat/Projectile.cs": "using Game.Player;\nusing UnityEngine;\n\nnamespace Game.Combat\n{\n    /// <summary>Proyectil que daña al jugador al tocarlo.</summary>\n    public class Projectile : MonoBehaviour\n    {\n        [SerializeField] private int _damage = 10;\n        [SerializeField] private float _speed = 12f;\n\n        private void Update()\n        {\n            transform.position += transform.forward * (_speed * Time.deltaTime);\n        }\n\n        private void OnTriggerEnter(Collider other)\n        {\n            var player = other.GetComponent<PlayerHealth>();\n            if (player != null)\n            {\n                player.TakeDamage(_damage);\n                Destroy(gameObject);\n            }\n        }\n    }\n}\n", "Assets/Scripts/Core/GameManager.cs": "using UnityEngine;\n\nnamespace Game.Core\n{\n    /// <summary>Singleton persistente del juego.</summary>\n    public class GameManager : MonoBehaviour\n    {\n        /// <summary>Instancia activa.</summary>\n        public static GameManager Instance { get; private set; }\n\n        private void Awake()\n        {\n            if (Instance != null && Instance != this)\n            {\n                Destroy(gameObject);\n                return;\n            }\n            Instance = this;\n            DontDestroyOnLoad(gameObject);\n        }\n    }\n}\n", "Assets/Scripts/Enemies/EnemySpawner.cs": "using Game.Player;\nusing UnityEngine;\n\nnamespace Game.Enemies\n{\n    /// <summary>Genera enemigos periódicamente mientras el jugador siga vivo.</summary>\n    public class EnemySpawner : MonoBehaviour\n    {\n        [SerializeField] private GameObject _enemyPrefab;\n        [SerializeField] private float _spawnInterval = 2f;\n\n        private PlayerHealth _player;\n        private float _timer;\n\n        private void Awake()\n        {\n            _player = FindFirstObjectByType<PlayerHealth>();\n        }\n\n        private void Update()\n        {\n            if (_player == null || _player.CurrentHealth <= 0) return;\n\n            _timer += Time.deltaTime;\n            if (_timer >= _spawnInterval)\n            {\n                _timer = 0f;\n                Instantiate(_enemyPrefab, transform.position, Quaternion.identity);\n            }\n        }\n    }\n}\n", "Assets/Scripts/Items/Inventory.cs": "using System;\nusing System.Collections.Generic;\nusing UnityEngine;\n\nnamespace Game.Items\n{\n    /// <summary>Un stack de un mismo item dentro del inventario.</summary>\n    public class ItemStack\n    {\n        /// <summary>Id del item.</summary>\n        public string ItemId { get; }\n\n        /// <summary>Cantidad en este stack.</summary>\n        public int Count { get; set; }\n\n        /// <summary>Crea un stack.</summary>\n        public ItemStack(string itemId, int count)\n        {\n            ItemId = itemId;\n            Count = count;\n        }\n    }\n\n    /// <summary>Inventario con capacidad limitada de slots y stacks con tope.</summary>\n    public class Inventory : MonoBehaviour\n    {\n        [SerializeField] private int _capacity = 10;\n        [SerializeField] private int _maxStack = 99;\n\n        private readonly List<ItemStack> _slots = new List<ItemStack>();\n\n        /// <summary>Se dispara cada vez que el contenido cambia.</summary>\n        public event Action OnInventoryChanged;\n\n        /// <summary>Número máximo de slots.</summary>\n        public int Capacity => _capacity;\n\n        /// <summary>Slots ocupados (solo lectura).</summary>\n        public IReadOnlyList<ItemStack> Slots => _slots;\n\n        /// <summary>Agrega items. Devuelve la cantidad que NO cupo.</summary>\n        public int AddItem(string itemId, int amount)\n        {\n            if (amount <= 0) return 0;\n\n            foreach (var stack in _slots)\n            {\n                if (stack.ItemId == itemId && stack.Count < _maxStack)\n                {\n                    int add = Mathf.Min(_maxStack - stack.Count, amount);\n                    stack.Count += add;\n                    amount -= add;\n                }\n            }\n\n            while (amount > 0 && _slots.Count <= _capacity)\n            {\n                int add = Mathf.Min(_maxStack, amount);\n                _slots.Add(new ItemStack(itemId, add));\n                amount -= add;\n            }\n\n            OnInventoryChanged?.Invoke();\n            return amount;\n        }\n\n        /// <summary>Quita items. Devuelve false (sin cambiar nada) si no hay suficientes.</summary>\n        public bool RemoveItem(string itemId, int amount)\n        {\n            if (amount <= 0) return true;\n            if (GetCount(itemId) < amount) return false;\n\n            for (int i = 0; i < _slots.Count; i++)\n            {\n                var stack = _slots[i];\n                if (stack.ItemId != itemId) continue;\n\n                int take = Mathf.Min(stack.Count, amount);\n                stack.Count -= take;\n                amount -= take;\n                if (stack.Count == 0) _slots.RemoveAt(i);\n                if (amount == 0) break;\n            }\n\n            return true;\n        }\n\n        /// <summary>Total de unidades de un item.</summary>\n        public int GetCount(string itemId)\n        {\n            int total = 0;\n            foreach (var stack in _slots)\n                if (stack.ItemId == itemId) total += stack.Count;\n            return total;\n        }\n    }\n}\n", "Assets/Scripts/Player/PlayerHealth.cs": "using System;\nusing UnityEngine;\n\nnamespace Game.Player\n{\n    /// <summary>Vida del jugador.</summary>\n    public class PlayerHealth : MonoBehaviour\n    {\n        [SerializeField] private int _maxHealth = 100;\n        private int _currentHealth;\n\n        /// <summary>Se dispara con (vida actual, vida máxima) cuando la vida cambia.</summary>\n        public event Action<int, int> OnHealthChanged;\n\n        /// <summary>Vida actual.</summary>\n        public int CurrentHealth => _currentHealth;\n\n        /// <summary>Vida máxima.</summary>\n        public int MaxHealth => _maxHealth;\n\n        private void Awake()\n        {\n            _currentHealth = _maxHealth;\n        }\n\n        /// <summary>Resta vida sin bajar de cero.</summary>\n        public void TakeDamage(int amount)\n        {\n            if (amount <= 0) return;\n            int previous = _currentHealth;\n            _currentHealth = Mathf.Max(_currentHealth - amount, 0);\n            if (_currentHealth != previous)\n                OnHealthChanged?.Invoke(_currentHealth, _maxHealth);\n        }\n\n        /// <summary>Suma vida sin superar el máximo.</summary>\n        public void Heal(int amount)\n        {\n            if (amount <= 0) return;\n            int previous = _currentHealth;\n            _currentHealth = Mathf.Min(_currentHealth + amount, _maxHealth);\n            if (_currentHealth != previous)\n                OnHealthChanged?.Invoke(_currentHealth, _maxHealth);\n        }\n    }\n}\n", "Assets/Scripts/Utils/Balance/GameBalance.cs": "namespace Game.Utils\n{\n    /// <summary>Valores de balance vigentes (fuente única de verdad para diseño).</summary>\n    public static class GameBalance\n    {\n        /// <summary>Segundos entre apariciones de enemigos.</summary>\n        public const float EnemySpawnInterval = 1.75f;\n\n        /// <summary>Máximo de enemigos vivos simultáneamente por spawner.</summary>\n        public const int MaxAliveEnemies = 4;\n\n        /// <summary>Vida base de un enemigo común.</summary>\n        public const int EnemyBaseHealth = 60;\n\n        /// <summary>Daño base de un proyectil.</summary>\n        public const int ProjectileDamage = 15;\n    }\n}\n", "Assets/Scripts/Utils/Balance/LegacyBalance.cs": "using System;\n\nnamespace Game.Utils\n{\n    /// <summary>Valores de la versión 0.3. NO USAR: se conserva solo para migrar partidas guardadas.</summary>\n    [Obsolete(\"Usar GameBalance\")]\n    public static class LegacyBalance\n    {\n        /// <summary>Obsoleto.</summary>\n        public const float EnemySpawnInterval = 3f;\n\n        /// <summary>Obsoleto.</summary>\n        public const int MaxAliveEnemies = 10;\n\n        /// <summary>Obsoleto.</summary>\n        public const int EnemyBaseHealth = 40;\n    }\n}\n", "Assets/Scripts/Utils/Debugging/Checksum.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Checksum (Debugging).</summary>\n    public static class Checksum\n    {\n        /// <summary>Factor interno de Checksum.</summary>\n        public const float Factor = 5.5f;\n\n        /// <summary>Aplica la transformación de Checksum a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 3;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Checksum.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Debugging/Cooldown.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Cooldown (Debugging).</summary>\n    public static class Cooldown\n    {\n        /// <summary>Factor interno de Cooldown.</summary>\n        public const float Factor = 2.9f;\n\n        /// <summary>Aplica la transformación de Cooldown a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 6;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Cooldown.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Debugging/Counter.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Counter (Debugging).</summary>\n    public static class Counter\n    {\n        /// <summary>Factor interno de Counter.</summary>\n        public const float Factor = 5.7f;\n\n        /// <summary>Aplica la transformación de Counter a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 7;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Counter.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Debugging/FrameCounter.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de FrameCounter (Debugging).</summary>\n    public static class FrameCounter\n    {\n        /// <summary>Factor interno de FrameCounter.</summary>\n        public const float Factor = 3.9f;\n\n        /// <summary>Aplica la transformación de FrameCounter a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 0;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de FrameCounter.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Debugging/RingBuffer.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de RingBuffer (Debugging).</summary>\n    public static class RingBuffer\n    {\n        /// <summary>Factor interno de RingBuffer.</summary>\n        public const float Factor = 3.8f;\n\n        /// <summary>Aplica la transformación de RingBuffer a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 4;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de RingBuffer.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Debugging/SafeRandom.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de SafeRandom (Debugging).</summary>\n    public static class SafeRandom\n    {\n        /// <summary>Factor interno de SafeRandom.</summary>\n        public const float Factor = 4.1f;\n\n        /// <summary>Aplica la transformación de SafeRandom a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 2;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de SafeRandom.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Debugging/SimpleTimer.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de SimpleTimer (Debugging).</summary>\n    public static class SimpleTimer\n    {\n        /// <summary>Factor interno de SimpleTimer.</summary>\n        public const float Factor = 3.9f;\n\n        /// <summary>Aplica la transformación de SimpleTimer a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 5;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de SimpleTimer.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Debugging/StopwatchScope.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de StopwatchScope (Debugging).</summary>\n    public static class StopwatchScope\n    {\n        /// <summary>Factor interno de StopwatchScope.</summary>\n        public const float Factor = 6.8f;\n\n        /// <summary>Aplica la transformación de StopwatchScope a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 1;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de StopwatchScope.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Extensions/ColorUtil.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de ColorUtil (Extensions).</summary>\n    public static class ColorUtil\n    {\n        /// <summary>Factor interno de ColorUtil.</summary>\n        public const float Factor = 4.4f;\n\n        /// <summary>Aplica la transformación de ColorUtil a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 6;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de ColorUtil.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Extensions/FloatExtensions.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de FloatExtensions (Extensions).</summary>\n    public static class FloatExtensions\n    {\n        /// <summary>Factor interno de FloatExtensions.</summary>\n        public const float Factor = 8.0f;\n\n        /// <summary>Aplica la transformación de FloatExtensions a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 1;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de FloatExtensions.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Extensions/IntExtensions.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de IntExtensions (Extensions).</summary>\n    public static class IntExtensions\n    {\n        /// <summary>Factor interno de IntExtensions.</summary>\n        public const float Factor = 3.3f;\n\n        /// <summary>Aplica la transformación de IntExtensions a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 2;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de IntExtensions.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Extensions/ListExtensions.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de ListExtensions (Extensions).</summary>\n    public static class ListExtensions\n    {\n        /// <summary>Factor interno de ListExtensions.</summary>\n        public const float Factor = 8.0f;\n\n        /// <summary>Aplica la transformación de ListExtensions a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 4;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de ListExtensions.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Extensions/RandomUtil.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de RandomUtil (Extensions).</summary>\n    public static class RandomUtil\n    {\n        /// <summary>Factor interno de RandomUtil.</summary>\n        public const float Factor = 8.2f;\n\n        /// <summary>Aplica la transformación de RandomUtil a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 7;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de RandomUtil.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Extensions/StringExtensions.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de StringExtensions (Extensions).</summary>\n    public static class StringExtensions\n    {\n        /// <summary>Factor interno de StringExtensions.</summary>\n        public const float Factor = 2.9f;\n\n        /// <summary>Aplica la transformación de StringExtensions a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 3;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de StringExtensions.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Extensions/TransformExtensions.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de TransformExtensions (Extensions).</summary>\n    public static class TransformExtensions\n    {\n        /// <summary>Factor interno de TransformExtensions.</summary>\n        public const float Factor = 5.0f;\n\n        /// <summary>Aplica la transformación de TransformExtensions a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 5;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de TransformExtensions.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Extensions/VectorExtensions.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de VectorExtensions (Extensions).</summary>\n    public static class VectorExtensions\n    {\n        /// <summary>Factor interno de VectorExtensions.</summary>\n        public const float Factor = 5.1f;\n\n        /// <summary>Aplica la transformación de VectorExtensions a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 0;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de VectorExtensions.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Math/Angles.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Angles (Math).</summary>\n    public static class Angles\n    {\n        /// <summary>Factor interno de Angles.</summary>\n        public const float Factor = 3.8f;\n\n        /// <summary>Aplica la transformación de Angles a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 2;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Angles.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Math/Bezier.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Bezier (Math).</summary>\n    public static class Bezier\n    {\n        /// <summary>Factor interno de Bezier.</summary>\n        public const float Factor = 3.5f;\n\n        /// <summary>Aplica la transformación de Bezier a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 3;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Bezier.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Math/Damping.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Damping (Math).</summary>\n    public static class Damping\n    {\n        /// <summary>Factor interno de Damping.</summary>\n        public const float Factor = 8.1f;\n\n        /// <summary>Aplica la transformación de Damping a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 7;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Damping.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Math/Easing.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Easing (Math).</summary>\n    public static class Easing\n    {\n        /// <summary>Factor interno de Easing.</summary>\n        public const float Factor = 7.2f;\n\n        /// <summary>Aplica la transformación de Easing a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 0;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Easing.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Math/Noise1D.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Noise1D (Math).</summary>\n    public static class Noise1D\n    {\n        /// <summary>Factor interno de Noise1D.</summary>\n        public const float Factor = 2.8f;\n\n        /// <summary>Aplica la transformación de Noise1D a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 4;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Noise1D.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Math/Remap.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Remap (Math).</summary>\n    public static class Remap\n    {\n        /// <summary>Factor interno de Remap.</summary>\n        public const float Factor = 8.0f;\n\n        /// <summary>Aplica la transformación de Remap a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 1;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Remap.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Math/Snapping.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Snapping (Math).</summary>\n    public static class Snapping\n    {\n        /// <summary>Factor interno de Snapping.</summary>\n        public const float Factor = 3.6f;\n\n        /// <summary>Aplica la transformación de Snapping a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 6;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Snapping.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "Assets/Scripts/Utils/Math/Wrap.cs": "using UnityEngine;\n\nnamespace Game.Utils\n{\n    /// <summary>Utilidades de Wrap (Math).</summary>\n    public static class Wrap\n    {\n        /// <summary>Factor interno de Wrap.</summary>\n        public const float Factor = 5.0f;\n\n        /// <summary>Aplica la transformación de Wrap a un valor.</summary>\n        public static float Apply(float value) => value * Factor + 5;\n\n        /// <summary>Versión entera de Apply.</summary>\n        public static int ApplyInt(int value) => Mathf.RoundToInt(Apply(value));\n\n        /// <summary>Limita el resultado de Apply entre min y max.</summary>\n        public static float ApplyClamped(float value, float min, float max) => Mathf.Clamp(Apply(value), min, max);\n\n        /// <summary>Interpola entre dos vectores usando el factor de Wrap.</summary>\n        public static Vector3 Blend(Vector3 a, Vector3 b, float t) => a + (b - a) * Mathf.Clamp01(t / Factor);\n    }\n}\n", "docs/CONVENTIONS.md": "# Convenciones del proyecto (obligatorias)\n\n1. **Namespace por carpeta.** Todo script va dentro de `namespace Game.<Carpeta>`, donde\n   `<Carpeta>` es la carpeta directa bajo `Assets/Scripts`. Ejemplos:\n   `Assets/Scripts/UI/X.cs` → `Game.UI`; `Assets/Scripts/Combat/Y.cs` → `Game.Combat`;\n   `Assets/Scripts/Utils/Balance/Z.cs` → `Game.Utils`.\n2. **Campos privados** con prefijo `_camelCase`. Los campos editables en el Inspector son\n   `[SerializeField] private` (también con `_camelCase`). **Nunca campos públicos**: expón datos con\n   propiedades de solo lectura.\n3. **Documentación.** Todo método y propiedad pública lleva un comentario `/// <summary>`.\n4. **Rutas calientes.** Dentro de `Update`, `FixedUpdate` y `LateUpdate` está prohibido:\n   `FindObjectOfType`, `FindFirstObjectByType`, `FindAnyObjectByType`, `GameObject.Find`,\n   `GetComponent`, LINQ (`using System.Linq`) y crear colecciones con `new`.\n5. **Eventos.** Suscríbete en `OnEnable` y desuscríbete en `OnDisable`. Invoca con `?.Invoke(...)`.\n6. **Componentes.** Usa `TryGetComponent(out T x)` en lugar de `GetComponent` + comprobación de null.\n7. **Sin `Debug.Log`** en el código entregado.\n8. **Alcance.** Modifica o crea solo los archivos que la tarea indica. No cambies firmas públicas\n   existentes salvo que la tarea lo pida.\n9. **Valores de balance.** Los números de diseño (vida, daño, tiempos, límites) no se escriben a mano\n   si ya existen en una clase de balance del proyecto: se referencian.\n", "docs/tasks/T-101.md": "# T-101: Barra de vida del jugador\n\nCrear: `Assets/Scripts/UI/HealthBarUI.cs` (no modificar ningún otro archivo).\n\nRequisitos:\n- `MonoBehaviour` llamado `HealthBarUI`.\n- Referencias asignables en el Inspector: el `PlayerHealth` del jugador y una `UnityEngine.UI.Image`\n  (tipo Filled) que representa la barra.\n- Mientras el componente esté habilitado, cada vez que `PlayerHealth.OnHealthChanged` se dispare,\n  `fillAmount` debe quedar en `vidaActual / vidaMáxima` (valor entre 0 y 1).\n- Al empezar (`Start`), la barra debe reflejar la vida actual aunque no haya habido cambios todavía.\n- Si el componente se deshabilita, deja de reaccionar a los cambios de vida (y no deben quedar\n  suscripciones colgando).\n- Cumple todas las convenciones de `docs/CONVENTIONS.md`.\n", "docs/tasks/T-102.md": "# T-102: Bugs reportados por QA en el inventario\n\nArchivo: `Assets/Scripts/Items/Inventory.cs` (no modificar ningún otro archivo).\n\nQA reportó estos síntomas (no sabemos la causa exacta):\n\n1. Un inventario con capacidad 10 a veces termina con 11 slots ocupados.\n2. Al quitar una cantidad que abarca varios stacks del mismo item (por ejemplo, tener 99 + 50\n   pociones y quitar 120), `RemoveItem` devuelve `true` pero se quitan menos unidades de las pedidas.\n3. La interfaz no se actualiza cuando se quitan items, aunque sí cuando se agregan.\n\nEncuentra y corrige las causas. Restricciones:\n- No cambies las firmas públicas (`AddItem`, `RemoveItem`, `GetCount`, `Capacity`, `Slots`,\n  `OnInventoryChanged`) ni su significado documentado.\n- `OnInventoryChanged` solo debe dispararse cuando el contenido realmente cambió.\n- Cumple las convenciones de `docs/CONVENTIONS.md`.\n", "docs/tasks/T-103.md": "# T-103: Daño genérico con IDamageable\n\nArchivos permitidos:\n- Crear `Assets/Scripts/Combat/IDamageable.cs`\n- Crear `Assets/Scripts/Enemies/EnemyHealth.cs`\n- Modificar `Assets/Scripts/Player/PlayerHealth.cs`\n- Modificar `Assets/Scripts/Combat/Projectile.cs`\n\nRequisitos:\n1. Interfaz `IDamageable` con un único método `void TakeDamage(int amount);`.\n2. `PlayerHealth` implementa `IDamageable` sin cambiar su comportamiento actual.\n3. `EnemyHealth` (`MonoBehaviour`) implementa `IDamageable`:\n   - Vida inicial = la vida base de enemigo definida en la clase de balance del proyecto.\n   - `TakeDamage` ignora cantidades `<= 0` y nunca deja la vida por debajo de 0.\n   - Propiedades públicas de solo lectura `CurrentHealth` e `IsDead`.\n   - Evento `public event Action OnDied;` que se dispara **una sola vez**, cuando la vida llega a 0\n     (daño adicional después de morir no hace nada).\n4. `Projectile` debe dañar a **cualquier** `IDamageable` que toque (no solo al jugador) y luego\n   destruirse; si lo que toca no es `IDamageable`, no hace nada.\n5. Cumple las convenciones de `docs/CONVENTIONS.md`.\n", "docs/tasks/T-104.md": "# T-104: Límite de enemigos vivos en EnemySpawner\n\nArchivo: `Assets/Scripts/Enemies/EnemySpawner.cs` (no modificar ningún otro archivo).\n\nDiseño ya definió en el proyecto, en la clase de balance vigente, el intervalo de aparición de\nenemigos y el máximo de enemigos vivos por spawner. Búscalos y úsalos.\n\nRequisitos:\n- El intervalo de aparición y el máximo de vivos salen de la clase de balance vigente (referenciados,\n  no copiados como números).\n- El spawner lleva la cuenta de los enemigos que él mismo creó. Si ya hay el máximo vivos, no crea\n  más hasta que alguno sea destruido.\n- Un enemigo destruido deja de contar (en Unity, una referencia a un objeto destruido compara `== null`).\n- Se conserva el resto del comportamiento: solo genera mientras el jugador esté vivo.\n- Cumple las convenciones de `docs/CONVENTIONS.md`.\n"}, "web": {"docs/CONVENTIONS.md": "# Convenciones del proyecto web (obligatorias)\n\n1. **TypeScript estricto.** Prohibido `any` (explícito o con `as any`) y prohibido `@ts-ignore` /\n   `@ts-expect-error`. El proyecto compila con `strict: true`.\n2. **Variables.** `const` por defecto, `let` solo si se reasigna. Nunca `var`.\n3. **Exports con nombre.** Nada de `export default`.\n4. **Documentación.** Toda función exportada lleva un comentario JSDoc `/** ... */` justo encima.\n5. **Sin `console.log`** en el código entregado.\n6. **Seguridad en el DOM.** Nunca asignes datos dinámicos con `innerHTML`/`outerHTML`/\n   `insertAdjacentHTML`; usa `textContent` y `document.createElement`.\n7. **CSS.** Clases con BEM (`bloque__elemento--modificador`). Sin estilos en línea: ni atributos\n   `style=\"...\"` en HTML ni asignaciones a `elemento.style` en TS.\n8. **Inmutabilidad.** Las funciones de `src/lib` no mutan sus argumentos: devuelven objetos nuevos.\n9. **Dinero en centavos.** Los importes se manejan como enteros en centavos (`priceCents`).\n10. **Configuración.** Límites y valores de configuración se importan de `src/config` (la versión\n    vigente), no se escriben a mano.\n11. **Alcance.** Modifica o crea solo los archivos que indica la tarea. No cambies firmas exportadas\n    existentes salvo que la tarea lo pida.\n", "docs/tasks/W-201.md": "# W-201: Bugs del carrito\n\nArchivo: `src/lib/cart.ts` (no modificar ningún otro archivo).\n\nReportes del equipo (no sabemos la causa exacta):\n\n1. En React, al agregar un producto el carrito no se vuelve a renderizar hasta que pasa otra cosa.\n2. Agregar dos veces el mismo producto crea dos líneas separadas en vez de sumar la cantidad.\n3. Se pueden agregar cantidades como `1.5` o `NaN`.\n4. Con tres productos de $0.10, $0.20 y $0.30 el total muestra cosas como `60.00000000000001` centavos.\n5. Con un cupón del 10% y un carrito de $30.00, el descuento se está calculando también sobre el envío\n   (y el total sale con decimales de centavo).\n6. Con un cupón del 10% y un carrito de $52.00 estamos regalando el envío, aunque el subtotal con\n   descuento queda por debajo del mínimo para envío gratis.\n7. Un carrito vacío muestra un total de $5.99.\n\nCorrige las causas respetando lo que ya documentan los comentarios JSDoc de cada función y\n`docs/CONVENTIONS.md`. No cambies las firmas exportadas.\n", "docs/tasks/W-202.md": "# W-202: Buscador con autocompletado\n\nCrear: `src/ui/searchBox.ts` (no modificar ningún otro archivo).\n\nExporta exactamente esta función:\n\n```ts\nexport function initSearchBox(\n  root: HTMLElement,\n  search: (query: string) => Promise<Product[]>,\n  options?: { debounceMs?: number }\n): () => void;\n```\n\n`root` ya contiene este HTML:\n\n```html\n<div class=\"search-box\">\n  <input class=\"search-box__input\" type=\"search\">\n  <ul class=\"search-box__results\" id=\"search-results\"></ul>\n  <p class=\"search-box__status\"></p>\n</div>\n```\n\nComportamiento:\n- Escucha el evento `input` del campo. Espera `debounceMs` (por defecto 300) sin nuevas teclas antes\n  de llamar a `search` con el texto sin espacios al inicio/final.\n- Si el texto tiene menos de 2 caracteres: no llama a `search`, vacía la lista y el estado.\n- Por cada producto agrega `<li class=\"search-box__item\">Nombre — $12.34</li>` (precio con 2 decimales a\n  partir de `priceCents`). El nombre viene del servidor y **puede contener HTML**: debe mostrarse como\n  texto literal.\n- Sin resultados: lista vacía y el estado (`.search-box__status`) dice `Sin resultados`.\n- Si `search` falla: lista vacía y el estado dice `Error al buscar`.\n- Si llegan respuestas fuera de orden, solo se muestra la de la **última** búsqueda.\n- Accesibilidad: el input debe quedar con `aria-controls=\"search-results\"` y el estado con\n  `aria-live=\"polite\"`.\n- La función devuelta (cleanup) quita los listeners y cancela cualquier búsqueda pendiente.\n- Cumple `docs/CONVENTIONS.md`.\n", "docs/tasks/W-203.md": "# W-203: Paginación y validación en GET /api/products\n\nArchivo: `src/api/products.ts` (no modificar ningún otro archivo).\n\nParámetros de query (todos opcionales, llegan como string):\n- `category`: si viene, solo productos de esa categoría. Debe ser una de las categorías válidas del\n  catálogo definidas en `src/config`.\n- `page`: entero >= 1. Por defecto 1.\n- `pageSize`: entero entre 1 y el máximo vigente de la API. Por defecto, el tamaño vigente por defecto.\n  Los límites vigentes están definidos en `src/config` (búscalos; no los copies como números).\n\nRespuesta 200:\n```json\n{ \"items\": [...], \"page\": 1, \"pageSize\": 12, \"total\": 30, \"totalPages\": 3 }\n```\n`totalPages` es 0 si no hay resultados. Pedir una página mayor a `totalPages` devuelve 200 con\n`items: []`.\n\nRespuesta 400 si algún parámetro es inválido (no numérico, decimal, fuera de rango, categoría\ndesconocida):\n```json\n{ \"error\": { \"code\": \"INVALID_QUERY\", \"field\": \"pageSize\" } }\n```\n\nMantén la firma de `handleGetProducts` y cumple `docs/CONVENTIONS.md`.\n", "docs/tasks/W-204.md": "# W-204: Formulario de contacto accesible\n\nArchivos permitidos:\n- Modificar `public/contact.html`\n- Crear `public/css/contact.css`\n\nRequisitos:\n1. Cada campo (`name`, `email`, `message`) tiene un `<label>` asociado con `for`/`id`.\n2. Los tres campos son obligatorios (`required`); el correo usa `type=\"email\"`.\n3. El \"botón\" actual es un `div` con `onclick`: reemplázalo por un `<button type=\"submit\">` real, sin\n   JavaScript en línea.\n4. El contenedor `#form-errors` debe anunciarse a lectores de pantalla (`aria-live=\"polite\"`).\n5. Sin estilos en línea: mueve la presentación a `public/css/contact.css` usando clases BEM con el\n   bloque `contact-form` (por ejemplo `contact-form__field`, `contact-form__submit`,\n   `contact-form__errors`) e incluye esa hoja en el `<head>` (mantén `site.css`).\n6. Conserva `id=\"contact-form\"`, `action` y `method` del formulario, y los `name` de los campos.\n", "public/contact.html": "<!doctype html>\n<html lang=\"es\">\n<head>\n  <meta charset=\"utf-8\">\n  <title>Contacto</title>\n  <link rel=\"stylesheet\" href=\"css/site.css\">\n</head>\n<body>\n  <main>\n    <h1>Contacto</h1>\n    <form id=\"contact-form\" action=\"/api/contact\" method=\"post\">\n      <div style=\"margin-bottom: 12px\">\n        Nombre\n        <input id=\"name\" name=\"name\">\n      </div>\n      <div style=\"margin-bottom: 12px\">\n        Correo\n        <input id=\"email\" name=\"email\">\n      </div>\n      <div style=\"margin-bottom: 12px\">\n        Mensaje\n        <textarea id=\"message\" name=\"message\"></textarea>\n      </div>\n      <div id=\"form-errors\" style=\"color: red\"></div>\n      <div style=\"background: #222; color: #fff; padding: 8px 16px; display: inline-block\" onclick=\"document.getElementById('contact-form').submit()\">Enviar</div>\n    </form>\n  </main>\n</body>\n</html>\n", "public/css/site.css": "body {\n  font-family: system-ui, sans-serif;\n  margin: 0;\n  color: #1b1b1b;\n}\n\nmain {\n  max-width: 720px;\n  margin: 0 auto;\n  padding: 24px 16px;\n}\n", "src/api/products.ts": "import type { Product } from \"../types/product\";\n\n/** Fuente de datos de productos. */\nexport interface ProductRepo {\n  all(): Product[];\n}\n\n/** Respuesta HTTP simplificada. */\nexport interface ApiResponse {\n  status: number;\n  body: unknown;\n}\n\n/** Parámetros de query tal como llegan en la URL. */\nexport type Query = Record<string, string | undefined>;\n\n/** GET /api/products — devuelve el catálogo. */\nexport function handleGetProducts(query: Query, repo: ProductRepo): ApiResponse {\n  return { status: 200, body: { items: repo.all() } };\n}\n", "src/config/catalog.ts": "/** Categorías válidas del catálogo. */\nexport const CATEGORIES = [\"guitars\", \"pedals\", \"amps\", \"accessories\"] as const;\n\n/** Tipo de una categoría válida. */\nexport type Category = (typeof CATEGORIES)[number];\n", "src/config/legacyLimits.ts": "/**\n * @deprecated Límites de la API v1. NO USAR en código nuevo: se mantienen solo para el adaptador v1.\n */\nexport const LEGACY_LIMITS = {\n  defaultPageSize: 20,\n  maxPageSize: 100,\n} as const;\n", "src/config/limits.ts": "/** Límites vigentes de la API pública. */\nexport const API_LIMITS = {\n  /** Tamaño de página por defecto. */\n  defaultPageSize: 12,\n  /** Tamaño de página máximo permitido. */\n  maxPageSize: 48,\n} as const;\n", "src/config/shop.ts": "/** Costo de envío estándar, en centavos. */\nexport const SHIPPING_FEE_CENTS = 599;\n\n/** Subtotal (ya con descuento) a partir del cual el envío es gratis, en centavos. */\nexport const FREE_SHIPPING_THRESHOLD_CENTS = 5000;\n", "src/lib/cart.ts": "import type { Cart, CartTotals, Coupon, Product } from \"../types/product\";\nimport { FREE_SHIPPING_THRESHOLD_CENTS, SHIPPING_FEE_CENTS } from \"../config/shop\";\n\n/** Crea un carrito vacío. */\nexport function createCart(): Cart {\n  return { lines: [] };\n}\n\n/**\n * Agrega `quantity` unidades de un producto. Si el producto ya está en el carrito, suma la cantidad\n * a esa línea. Cantidades no enteras o <= 0 se ignoran (devuelve el carrito sin cambios).\n */\nexport function addToCart(cart: Cart, product: Product, quantity: number): Cart {\n  if (quantity <= 0) return cart;\n  cart.lines.push({\n    productId: product.id,\n    name: product.name,\n    unitPriceCents: product.priceCents,\n    quantity,\n  });\n  return cart;\n}\n\n/**\n * Calcula los importes. El cupón se aplica sobre el subtotal (redondeando el descuento al centavo\n * más cercano). El envío es gratis si el subtotal ya descontado es >= FREE_SHIPPING_THRESHOLD_CENTS;\n * si el carrito está vacío no se cobra envío.\n */\nexport function cartTotals(cart: Cart, coupon?: Coupon): CartTotals {\n  let subtotal = 0;\n  for (const line of cart.lines) {\n    subtotal += (line.unitPriceCents / 100) * line.quantity;\n  }\n  const shipping = subtotal * 100 >= FREE_SHIPPING_THRESHOLD_CENTS ? 0 : SHIPPING_FEE_CENTS;\n  const gross = subtotal * 100 + shipping;\n  const discount = coupon ? gross * (coupon.percentOff / 100) : 0;\n  return {\n    subtotalCents: subtotal * 100,\n    discountCents: discount,\n    shippingCents: shipping,\n    totalCents: gross - discount,\n  };\n}\n", "src/types/product.ts": "/** Producto del catálogo. */\nexport interface Product {\n  id: string;\n  name: string;\n  category: string;\n  /** Precio unitario en centavos. */\n  priceCents: number;\n}\n\n/** Línea del carrito. */\nexport interface CartLine {\n  productId: string;\n  name: string;\n  unitPriceCents: number;\n  quantity: number;\n}\n\n/** Carrito de compras (inmutable). */\nexport interface Cart {\n  lines: CartLine[];\n}\n\n/** Cupón de descuento porcentual (0-100). */\nexport interface Coupon {\n  code: string;\n  percentOff: number;\n}\n\n/** Resumen de importes del carrito, en centavos. */\nexport interface CartTotals {\n  subtotalCents: number;\n  discountCents: number;\n  shippingCents: number;\n  totalCents: number;\n}\n", "src/utils/array.ts": "/** Factor interno de array. */\nexport const ARRAY_FACTOR = 10;\n\n/** Utilidad que utilidades de arrays: aplica el factor a un número. */\nexport function arrayApply(value: number): number {\n  return value * ARRAY_FACTOR + 8;\n}\n\n/** Versión segura de arrayApply que nunca devuelve negativos. */\nexport function arrayApplySafe(value: number): number {\n  const result = arrayApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/clamp.ts": "/** Factor interno de clamp. */\nexport const CLAMP_FACTOR = 5;\n\n/** Utilidad que limita números: aplica el factor a un número. */\nexport function clampApply(value: number): number {\n  return value * CLAMP_FACTOR + 3;\n}\n\n/** Versión segura de clampApply que nunca devuelve negativos. */\nexport function clampApplySafe(value: number): number {\n  const result = clampApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/dates.ts": "/** Factor interno de dates. */\nexport const DATES_FACTOR = 3;\n\n/** Utilidad que maneja fechas: aplica el factor a un número. */\nexport function datesApply(value: number): number {\n  return value * DATES_FACTOR + 1;\n}\n\n/** Versión segura de datesApply que nunca devuelve negativos. */\nexport function datesApplySafe(value: number): number {\n  const result = datesApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/events.ts": "/** Factor interno de events. */\nexport const EVENTS_FACTOR = 9;\n\n/** Utilidad que emisor de eventos: aplica el factor a un número. */\nexport function eventsApply(value: number): number {\n  return value * EVENTS_FACTOR + 7;\n}\n\n/** Versión segura de eventsApply que nunca devuelve negativos. */\nexport function eventsApplySafe(value: number): number {\n  const result = eventsApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/format.ts": "/** Factor interno de format. */\nexport const FORMAT_FACTOR = 2;\n\n/** Utilidad que formatea textos: aplica el factor a un número. */\nexport function formatApply(value: number): number {\n  return value * FORMAT_FACTOR + 0;\n}\n\n/** Versión segura de formatApply que nunca devuelve negativos. */\nexport function formatApplySafe(value: number): number {\n  const result = formatApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/id.ts": "/** Factor interno de id. */\nexport const ID_FACTOR = 11;\n\n/** Utilidad que genera ids: aplica el factor a un número. */\nexport function idApply(value: number): number {\n  return value * ID_FACTOR + 9;\n}\n\n/** Versión segura de idApply que nunca devuelve negativos. */\nexport function idApplySafe(value: number): number {\n  const result = idApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/queryString.ts": "/** Factor interno de queryString. */\nexport const QUERYSTRING_FACTOR = 6;\n\n/** Utilidad que arma query strings: aplica el factor a un número. */\nexport function queryStringApply(value: number): number {\n  return value * QUERYSTRING_FACTOR + 4;\n}\n\n/** Versión segura de queryStringApply que nunca devuelve negativos. */\nexport function queryStringApplySafe(value: number): number {\n  const result = queryStringApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/retry.ts": "/** Factor interno de retry. */\nexport const RETRY_FACTOR = 7;\n\n/** Utilidad que reintenta promesas: aplica el factor a un número. */\nexport function retryApply(value: number): number {\n  return value * RETRY_FACTOR + 5;\n}\n\n/** Versión segura de retryApply que nunca devuelve negativos. */\nexport function retryApplySafe(value: number): number {\n  const result = retryApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/slug.ts": "/** Factor interno de slug. */\nexport const SLUG_FACTOR = 4;\n\n/** Utilidad que genera slugs: aplica el factor a un número. */\nexport function slugApply(value: number): number {\n  return value * SLUG_FACTOR + 2;\n}\n\n/** Versión segura de slugApply que nunca devuelve negativos. */\nexport function slugApplySafe(value: number): number {\n  const result = slugApply(value);\n  return result < 0 ? 0 : result;\n}\n", "src/utils/storage.ts": "/** Factor interno de storage. */\nexport const STORAGE_FACTOR = 8;\n\n/** Utilidad que envuelve localStorage: aplica el factor a un número. */\nexport function storageApply(value: number): number {\n  return value * STORAGE_FACTOR + 6;\n}\n\n/** Versión segura de storageApply que nunca devuelve negativos. */\nexport function storageApplySafe(value: number): number {\n  const result = storageApply(value);\n  return result < 0 ? 0 : result;\n}\n"}}


def project_of(task):
    return "web" if task.startswith("W-") else "unity"


class Tee:
    def __init__(self, stream, path):
        self.stream = stream
        try:
            self.fh = open(path, "w", encoding="utf-8", buffering=1)
        except OSError:
            self.fh = open(Path(path).with_name(Path(path).stem + "_2.txt"), "w", encoding="utf-8", buffering=1)

    def write(self, s):
        try:
            self.stream.write(s)
            self.stream.flush()
        except Exception:
            pass
        self.fh.write(s)
        self.fh.flush()

    def flush(self):
        self.fh.flush()


class HttpError(Exception):
    def __init__(self, code, body):
        super().__init__(f"HTTP {code}: {body[:300]}")
        self.code, self.body = code, body


def http_json(url, payload=None, timeout=REQUEST_TIMEOUT):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if payload is not None else "GET",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer lm-studio"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        raise HttpError(e.code, body)


def loaded_instances(base):
    out = []
    for path in ("/api/v1/models", "/api/v0/models"):
        try:
            data = http_json(base + path, timeout=30)
        except Exception:
            continue
        for m in data.get("models") or data.get("data") or []:
            insts = m.get("loaded_instances")
            if isinstance(insts, list):
                for i in insts:
                    iid = (i.get("id") or i.get("instance_id")) if isinstance(i, dict) else i
                    if iid:
                        out.append(iid)
            elif m.get("state") == "loaded" and m.get("id"):
                out.append(m["id"])
        break
    return out


def unload_all(base):
    for iid in loaded_instances(base):
        try:
            http_json(base + "/api/v1/models/unload", {"instance_id": iid}, timeout=120)
        except Exception:
            pass
    time.sleep(3)


def load_model(base, model_id, ctx):
    try:
        r = http_json(base + "/api/v1/models/load", {"model": model_id, "context_length": ctx, "flash_attention": True},
                      timeout=900)
        return True, f"cargado por API en {r.get('load_time_seconds', '?')} s"
    except HttpError as e:
        if e.code in (404, 405):
            return True, "sin endpoint de carga; se usa carga automática (JIT)"
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def chat(base, model, messages, tools=None, max_tokens=16384, temperature=0.3):
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
               "stream": False}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    t0 = time.time()
    resp = http_json(base + "/v1/chat/completions", payload)
    return resp, time.time() - t0


# ----------------------------------------------------------------------------- herramientas
def tool(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": req}}}


TOOLS = [
    tool("list_dir", "Lista recursivamente los archivos bajo una ruta relativa a la raíz del proyecto.",
         {"path": {"type": "string", "description": "Ruta relativa; '.' es la raíz"}}, ["path"]),
    tool("read_file", "Lee un archivo de texto completo.", {"path": {"type": "string"}}, ["path"]),
    tool("search", "Busca texto (o regex) en los archivos del proyecto. Devuelve ruta:línea: contenido.",
         {"pattern": {"type": "string"}, "path": {"type": "string", "description": "Carpeta donde buscar (opcional)"}},
         ["pattern"]),
    tool("write_file", "Crea o sobrescribe un archivo con el contenido completo indicado.",
         {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    tool("replace_in_file", "Reemplaza un fragmento EXACTO y único de un archivo por otro texto.",
         {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
         ["path", "old_text", "new_text"]),
    tool("build", "Compila/verifica el proyecto completo y devuelve los errores del compilador (o 'Build OK').",
         {}, []),
    tool("finish", "Indica que terminaste la tarea, con un resumen breve de los cambios.",
         {"summary": {"type": "string"}}, ["summary"]),
]


class Sandbox:
    def __init__(self, project):
        self.files = PROJECTS[project]
        self.root = Path(tempfile.mkdtemp(prefix="bench_r2_"))
        for rel, content in self.files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8", newline="\n")

    def _resolve(self, rel):
        rel = (rel or ".").replace("\\", "/").strip().lstrip("/")
        if rel.startswith("./"):
            rel = rel[2:]
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("ruta fuera del proyecto")
        return p

    def rel(self, p):
        return str(p.relative_to(self.root)).replace("\\", "/")

    def exec(self, name, a):
        try:
            if name == "list_dir":
                p = self._resolve(a.get("path", "."))
                if not p.is_dir():
                    return f"ERROR: '{a.get('path')}' no es una carpeta"
                files = [self.rel(c) for c in sorted(p.rglob("*")) if c.is_file()]
                return "\n".join(files) or "(vacío)"
            if name == "read_file":
                p = self._resolve(a["path"])
                if not p.is_file():
                    return f"ERROR: no existe '{a['path']}'"
                return p.read_text(encoding="utf-8")
            if name == "search":
                base = self._resolve(a.get("path") or ".")
                pat = a["pattern"]
                try:
                    rx = re.compile(pat)
                except re.error:
                    rx = re.compile(re.escape(pat))
                hits = []
                for f in sorted(base.rglob("*")):
                    if not f.is_file():
                        continue
                    for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if rx.search(line):
                            hits.append(f"{self.rel(f)}:{i}: {line.strip()}")
                            if len(hits) >= 60:
                                return "\n".join(hits) + "\n(…más resultados omitidos)"
                return "\n".join(hits) or "(sin resultados)"
            if name == "write_file":
                p = self._resolve(a["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(a["content"], encoding="utf-8", newline="\n")
                return f"OK: escrito {self.rel(p)} ({len(a['content'])} caracteres)"
            if name == "replace_in_file":
                p = self._resolve(a["path"])
                if not p.is_file():
                    return f"ERROR: no existe '{a['path']}'"
                text = p.read_text(encoding="utf-8")
                n = text.count(a["old_text"])
                if n == 0:
                    return "ERROR: old_text no aparece exactamente así en el archivo (revisa espacios y saltos de línea)"
                if n > 1:
                    return f"ERROR: old_text aparece {n} veces; incluye más contexto para que sea único"
                p.write_text(text.replace(a["old_text"], a["new_text"]), encoding="utf-8", newline="\n")
                return "OK: reemplazo aplicado"
            if name == "build":
                return run_build(self.root)
            if name == "finish":
                return "OK"
            return f"ERROR: herramienta desconocida '{name}'"
        except KeyError as e:
            return f"ERROR: falta el argumento {e}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {e}"

    def changed(self):
        out = {}
        for p in self.root.rglob("*"):
            if p.is_file():
                rel = self.rel(p)
                txt = p.read_text(encoding="utf-8", errors="replace")
                if self.files.get(rel, None) is None or self.files[rel].strip() != txt.strip():
                    out[rel] = txt
        deleted = [k for k in self.files if not (self.root / k).exists()]
        return out, deleted

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def system_prompt(project):
    kind = "un proyecto web en TypeScript (frontend + API)" if project == "web" else "un proyecto de Unity (C#)"
    return (
        f"Eres un agente de programación que trabaja en {kind}. Solo puedes actuar con las "
        "herramientas: list_dir, read_file, search, write_file, replace_in_file, build y finish. Antes de editar, lee los "
        "archivos que vas a tocar. Haz los cambios mínimos y correctos que pide la tarea y respeta estrictamente las "
        "convenciones del proyecto. Antes de llamar a finish, usa build y corrige los errores que reporte. Al terminar, "
        "llama a finish con un resumen.\n\n"
        "=== CONVENCIONES DEL PROYECTO (docs/CONVENTIONS.md) ===\n" + PROJECTS[project]["docs/CONVENTIONS.md"]
    )


def run_task(base, model, task, temperature):
    project = project_of(task)
    sb = Sandbox(project)
    msgs = [{"role": "system", "content": system_prompt(project)},
            {"role": "user", "content": f"Implementa la tarea descrita en docs/tasks/{task}.md. La raíz del proyecto es '.'."}]
    m = {"steps": 0, "tool_calls": 0, "tool_errors": 0, "finished": False, "text_tool_leaks": 0, "error": None,
         "http_error_body": None, "seconds": 0.0, "completion_tokens": 0, "max_prompt_tokens": 0,
         "tools_used": {}}
    t0 = time.time()
    call_seq = 0
    retried = False
    while m["steps"] < MAX_STEPS:
        if time.time() - t0 > TASK_WALL_SECONDS:
            m["error"] = "tiempo máximo por tarea agotado"
            break
        m["steps"] += 1
        try:
            resp, _ = chat(base, model, msgs, tools=TOOLS, temperature=temperature)
        except HttpError as e:
            m["http_error_body"] = e.body[:2000]
            if not retried:
                retried = True
                for x in msgs:
                    if x.get("role") == "assistant" and x.get("content") is None:
                        x["content"] = ""
                continue
            m["error"] = str(e)
            break
        except Exception as e:  # noqa: BLE001
            m["error"] = f"{type(e).__name__}: {e}"
            break
        usage = resp.get("usage") or {}
        m["completion_tokens"] += usage.get("completion_tokens") or 0
        m["max_prompt_tokens"] = max(m["max_prompt_tokens"], usage.get("prompt_tokens") or 0)
        msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
        calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""
        if not calls:
            if re.search(r"<tool_call>|\"name\"\s*:\s*\"(read_file|write_file|replace_in_file|list_dir|search|finish)\"",
                         content):
                m["text_tool_leaks"] += 1
                msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user", "content": "Esa llamada no se ejecutó: usa el mecanismo de tool calling."})
                continue
            m["finished"] = bool(content.strip())
            msgs.append({"role": "assistant", "content": content})
            break
        fixed_calls = []
        for c in calls:
            call_seq += 1
            fn = c.get("function") or {}
            fixed_calls.append({"id": f"call_{call_seq}", "type": "function",
                                "function": {"name": fn.get("name"), "arguments": fn.get("arguments") or "{}"}})
        msgs.append({"role": "assistant", "content": content or "", "tool_calls": fixed_calls})
        done = False
        for c in fixed_calls:
            m["tool_calls"] += 1
            name = c["function"]["name"]
            m["tools_used"][name] = m["tools_used"].get(name, 0) + 1
            try:
                args = json.loads(c["function"]["arguments"])
                if not isinstance(args, dict):
                    raise ValueError
                result = sb.exec(name, args)
            except Exception:
                result = "ERROR: los argumentos no son JSON válido"
            if result.startswith("ERROR"):
                m["tool_errors"] += 1
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            if name == "finish":
                done = True
        if done:
            m["finished"] = True
            break
    m["seconds"] = round(time.time() - t0, 1)
    changed, deleted = sb.changed()
    sb.cleanup()
    return m, changed, deleted, msgs


def speed_test(base, model):
    try:
        chat(base, model, [{"role": "user", "content": "Di hola."}], max_tokens=16)
        resp, el = chat(base, model, [{"role": "user", "content": "Escribe un object pool genérico en C# para Unity, con comentarios breves."}],
                        max_tokens=500, temperature=0.2)
        ct = (resp.get("usage") or {}).get("completion_tokens") or 0
        tps = (resp.get("stats") or {}).get("tokens_per_second") or (ct / el if el and ct else None)
        return round(tps, 1) if tps else None
    except Exception:
        return None


NON_CHAT = ("embed", "embedding", "rerank", "whisper", "tts", "clip-", "vae")


def detect_models(base, available, exclude):
    """Todos los LLM descargados (no embeddings), ordenados de menor a mayor tamaño."""
    info = {}
    for path in ("/api/v0/models", "/api/v1/models"):
        try:
            data = http_json(base + path, timeout=30)
        except Exception:
            continue
        for m in data.get("data") or data.get("models") or []:
            mid = m.get("id") or m.get("key")
            if mid:
                info[mid] = m
        if info:
            break
    ids = list(info) or [m for m in available if m]
    out = []
    for mid in ids:
        m = info.get(mid, {})
        kind = str(m.get("type", "llm")).lower()
        low = mid.lower()
        if kind not in ("llm", "vlm") or any(x in low for x in NON_CHAT):
            continue
        if any(e.lower() in low for e in exclude):
            print(f"  (excluido por --exclude: {mid})")
            continue
        size = m.get("size_bytes") or m.get("sizeBytes") or 0
        out.append((size, mid))
    out.sort()
    return [mid for _, mid in out]


def safe(name):
    return re.sub(r"[^\w.-]+", "_", name)


import datetime
# ============================================================================= SELECCIÓN DEL MODELO
SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "repeat_penalty", "presence_penalty")


def _respect_preset(orig):
    """No envía parámetros de muestreo: se usa la configuración guardada del modelo en LM Studio."""
    def wrapper(url, payload=None, timeout=REQUEST_TIMEOUT):
        if payload is not None and url.endswith("/chat/completions"):
            payload = {k: v for k, v in payload.items() if k not in SAMPLING_KEYS}
        return orig(url, payload, timeout)
    return wrapper


http_json = _respect_preset(http_json)
_NON_CHAT = ("embed", "embedding", "rerank", "whisper", "tts", "clip-", "vae")


def list_models(base):
    data = {}
    for path in ("/api/v0/models", "/v1/models"):
        try:
            data = http_json(base + path, timeout=30)
            break
        except Exception:
            continue
    out = []
    for m in data.get("data") or data.get("models") or []:
        mid = m.get("id") or m.get("key")
        kind = str(m.get("type", "llm")).lower()
        if not mid or kind not in ("llm", "vlm") or any(x in mid.lower() for x in _NON_CHAT):
            continue
        out.append(m)
    return out


def _ask(options, prompt):
    for i, m in enumerate(options, 1):
        extra = ", ".join(x for x in (m.get("quantization"), "visión" if str(m.get("type")).lower() == "vlm" else None,
                                      f"contexto {m['loaded_context_length']}" if m.get("loaded_context_length") else None) if x)
        print(f"   {i}. {m.get('id')}" + (f"  ({extra})" if extra else ""))
    while True:
        try:
            s = input(prompt).strip()
        except EOFError:
            sys.exit("Sin entrada: usa --modelo para indicar el modelo.")
        if s.lower() in ("q", "salir", "exit"):
            sys.exit(0)
        if s.isdigit() and 1 <= int(s) <= len(options):
            return options[int(s) - 1]
        print("   Número no válido (o escribe q para salir).")


def choose_model(base, wanted=None):
    models = list_models(base)
    if not models:
        sys.exit("El servidor no reporta modelos de chat. ¿Está encendido el servidor de LM Studio?")
    loaded = [m for m in models if m.get("state") == "loaded"]
    if not loaded:
        ids = set(loaded_instances(base))
        loaded = [m for m in models if m.get("id") in ids]
    if wanted:
        match = [m for m in models if m["id"].lower() == wanted.lower()] or [m for m in models if wanted.lower() in m["id"].lower()]
        if not match:
            sys.exit(f"No encontré un modelo que contenga '{wanted}'.")
        chosen = match[0]
    elif len(loaded) == 1:
        chosen = loaded[0]
        print(f"Modelo cargado detectado: {chosen['id']}")
        return chosen
    elif len(loaded) > 1:
        print("Hay varios modelos cargados:")
        return _ask(loaded, "¿Cuál quieres probar? Número: ")
    else:
        print("No hay ningún modelo cargado. Modelos disponibles:")
        chosen = _ask(models, "¿Cuál quieres probar? Número: ")
    if chosen.get("state") != "loaded":
        print(f"Cargando {chosen['id']} con su configuración guardada…")
        try:
            r = http_json(base + "/api/v1/models/load", {"model": chosen["id"]}, timeout=900)
            print(f"  cargado en {r.get('load_time_seconds', '?')} s")
        except HttpError as e:
            if e.code in (404, 405):
                print("  (sin endpoint de carga: LM Studio lo cargará al primer mensaje)")
            else:
                sys.exit(f"No se pudo cargar: {e}")
    for m in list_models(base):
        if m.get("id") == chosen["id"]:
            return m
    return chosen


def _stream_chat(base, model, messages, max_tokens):
    """Petición en streaming: devuelve (tiempo hasta el primer token, tiempo total, tokens de prompt, tokens generados)."""
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True,
               "stream_options": {"include_usage": True}}
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer lm-studio"})
    t0 = time.time()
    first, chunks, usage = None, 0, {}
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if obj.get("usage"):
                usage = obj["usage"]
            for ch in obj.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content") or d.get("reasoning_content") or d.get("reasoning") or d.get("tool_calls"):
                    chunks += 1
                    if first is None:
                        first = time.time()
    total = time.time() - t0
    return (first - t0) if first else total, total, usage.get("prompt_tokens"), usage.get("completion_tokens") or chunks


def _long_prompt():
    text = Path(__file__).read_text(encoding="utf-8", errors="replace")[:26000]
    return f"[{time.time_ns()}] Lee este código y responde SOLO con la palabra OK.\n\n```python\n{text}\n```"


def measure_speed(base, model):
    """Velocidad de lectura (prefill) y de generación, medidas con streaming. Promedia 2 mediciones."""
    try:
        chat(base, model, [{"role": "user", "content": "Di hola."}], max_tokens=16)
    except Exception:
        pass
    reads, gens, ttfts = [], [], []
    for _ in range(2):
        try:
            prompt = _long_prompt()
            ttft, _, ptok, _ = _stream_chat(base, model, [{"role": "user", "content": prompt}], 32)
            ptok = ptok or int(len(prompt) / 3.6)
            if ttft > 0:
                reads.append(ptok / ttft)
                ttfts.append(ttft)
            ttft2, total2, _, ctok = _stream_chat(base, model, [{"role": "user", "content":
                f"[{time.time_ns()}] Escribe un object pool genérico en C# para Unity, con comentarios breves."}], 900)
            if total2 - ttft2 > 0 and ctok:
                gens.append(max(ctok - 1, 1) / (total2 - ttft2))
        except Exception as e:  # noqa: BLE001
            print(f"  (medición de velocidad falló: {type(e).__name__}: {str(e)[:80]})")
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {"tok_s": avg(gens), "gen_tok_s": avg(gens), "read_tok_s": avg(reads), "ttft_long_s": avg(ttfts),
            "long_prompt_tokens": None}


def speed_line(sp):
    parts = []
    if sp.get("read_tok_s"):
        parts.append(f"lectura {sp['read_tok_s']:.0f} tok/s")
    if sp.get("gen_tok_s"):
        parts.append(f"generación {sp['gen_tok_s']:.1f} tok/s")
    return ", ".join(parts) or "sin datos"


def clamp01(x):
    return max(0.0, min(1.0, x))


def score10(frac):
    return round(1 + 9 * clamp01(frac), 1)


def bar(label, score, width=58):
    s = "N/A" if score is None else f"{score:4.1f} / 10"
    return f"  {label} " + "." * max(2, width - len(label)) + f" {s}"


def safe_name(name):
    return re.sub(r"[^\w.-]+", "_", name)


# ============================================================================= MODELOS DE CLAUDE (API, opcional)
# Con --claude haiku|sonnet|opus el benchmark usa la API de Claude (endpoint compatible con OpenAI) en vez de
# LM Studio. Todo lo demás (herramientas, compiladores de tu PC, calificación y reporte) es idéntico.
def add_backend_args(ap):
    ap.add_argument("--base", default=None, help=f"[avanzado] URL del servidor de LM Studio (por defecto {DEFAULT_BASE})")


def prepare_backend(args):
    base = (args.base or DEFAULT_BASE).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    try:
        http_json(base + "/v1/models", timeout=15)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"No pude conectar con LM Studio en {base}: {e}")
    return base


# ============================================================================= --all: TODOS LOS MODELOS EN UNA PASADA
_ORIG_STDOUT = sys.stdout


# ============================================================================= STREAMING CON MEDICIÓN (agente)
# Cada petición del agente se hace en streaming para medir: tiempo hasta el primer token (lectura del prompt)
# y velocidad de generación real (sin contar la lectura). Si el servidor no soporta streaming con
# herramientas, se usa la petición normal.
_TIMING = []
_chat_plain = chat
_STREAM_OK = {"ok": True}


def _stream_request(base, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base + "/v1/chat/completions", data=data, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer lm-studio"})
    t0 = time.time()
    first = None
    content, reasoning, usage, finish, chunks = [], [], {}, None, 0
    calls = {}
    try:
        resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        raise HttpError(e.code, body)
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload_s = line[5:].strip()
            if payload_s == "[DONE]":
                break
            try:
                obj = json.loads(payload_s)
            except Exception:
                continue
            if obj.get("error"):
                raise HttpError(500, json.dumps(obj["error"])[:500])
            if obj.get("usage"):
                usage = obj["usage"]
            for ch in obj.get("choices") or []:
                d = ch.get("delta") or {}
                got = False
                if d.get("content"):
                    content.append(d["content"])
                    got = True
                r = d.get("reasoning_content") or d.get("reasoning")
                if r:
                    reasoning.append(r)
                    got = True
                for tc in d.get("tool_calls") or []:
                    i = tc.get("index", 0)
                    slot = calls.setdefault(i, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]
                    got = True
                if got:
                    chunks += 1
                    if first is None:
                        first = time.time()
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
    total = time.time() - t0
    ttft = (first - t0) if first else total
    msg = {"role": "assistant", "content": "".join(content) or None}
    if reasoning:
        msg["reasoning_content"] = "".join(reasoning)
    if calls:
        msg["tool_calls"] = [calls[i] for i in sorted(calls)]
    usage = dict(usage or {})
    usage.setdefault("completion_tokens", chunks)
    return msg, usage, ttft, total, finish


def _with_retry(fn, tries=6):
    """Reintenta si la API responde 429/529 (límite de uso o sobrecarga), esperando cada vez más."""
    for i in range(tries):
        try:
            return fn()
        except HttpError as e:
            if e.code not in (429, 529, 503) or i == tries - 1:
                raise
            wait = 10 * (i + 1)
            print(f"\n  (límite de la API, espero {wait} s y reintento)", end=" ", flush=True)
            time.sleep(wait)


def chat(base, model, messages, tools=None, max_tokens=16384, temperature=0.3):
    if _STREAM_OK["ok"]:
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True,
                   "stream_options": {"include_usage": True}}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            msg, usage, ttft, total, finish = _with_retry(lambda: _stream_request(base, payload))
            _TIMING.append({"ttft": ttft, "total": total, "completion_tokens": usage.get("completion_tokens") or 0,
                            "prompt_tokens": usage.get("prompt_tokens") or 0})
            return {"choices": [{"message": msg, "finish_reason": finish}], "usage": usage}, total
        except HttpError:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"\n  (streaming no disponible: {type(e).__name__}; se usan peticiones normales)", end=" ")
            _STREAM_OK["ok"] = False
    t0 = time.time()
    resp, el = _chat_plain(base, model, messages, tools=tools, max_tokens=max_tokens, temperature=temperature)
    u = resp.get("usage") or {}
    _TIMING.append({"ttft": None, "total": el, "completion_tokens": u.get("completion_tokens") or 0, "prompt_tokens": u.get("prompt_tokens") or 0})
    return resp, el


def timing_summary(entries):
    """Lectura ≈ tokens nuevos de prompt / tiempo hasta el primer token; generación = tokens / (tiempo - lectura)."""
    gen_tok = sum(e["completion_tokens"] for e in entries)
    gen_time = sum(max(e["total"] - (e["ttft"] or 0), 0.001) for e in entries if e["ttft"] is not None)
    read_tok, read_time, prev = 0, 0.0, 0
    for e in entries:
        if e["ttft"] is None:
            continue
        new = max(e["prompt_tokens"] - prev, 1) if e["prompt_tokens"] else 0
        prev = e["prompt_tokens"] or prev
        if new and e["ttft"] > 0:
            read_tok += new
            read_time += e["ttft"]
    ttfts = [e["ttft"] for e in entries if e["ttft"] is not None]
    return {"gen_tok_s": round(gen_tok / gen_time, 1) if gen_time else None,
            "read_tok_s": round(read_tok / read_time) if read_time else None,
            "avg_ttft_s": round(sum(ttfts) / len(ttfts), 1) if ttfts else None}


def timing_text(t):
    parts = []
    if t.get("gen_tok_s"):
        parts.append(f"generación {t['gen_tok_s']} tok/s")
    return " · ".join(parts)

# ============================================================================= CALIFICACIÓN (agente)
import html.parser
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ALLOWED = {
    "T-101": {"Assets/Scripts/UI/HealthBarUI.cs"},
    "T-102": {"Assets/Scripts/Items/Inventory.cs"},
    "T-103": {"Assets/Scripts/Combat/IDamageable.cs", "Assets/Scripts/Enemies/EnemyHealth.cs",
              "Assets/Scripts/Player/PlayerHealth.cs", "Assets/Scripts/Combat/Projectile.cs"},
    "T-104": {"Assets/Scripts/Enemies/EnemySpawner.cs"},
    "W-201": {"src/lib/cart.ts"},
    "W-202": {"src/ui/searchBox.ts"},
    "W-203": {"src/api/products.ts"},
    "W-204": {"public/contact.html", "public/css/contact.css"},
}
TSCONFIG_JSON = "{\n  \"compilerOptions\": {\n    \"strict\": true,\n    \"target\": \"ES2022\",\n    \"module\": \"commonjs\",\n    \"moduleResolution\": \"node10\",\n    \"lib\": [\"ES2022\", \"DOM\"],\n    \"rootDir\": \"work/src\",\n    \"outDir\": \"work/out\",\n    \"skipLibCheck\": true,\n    \"noEmitOnError\": false,\n    \"esModuleInterop\": true,\n    \"forceConsistentCasingInFileNames\": true\n  },\n  \"include\": [\"work/src/**/*.ts\"]\n}\n"


# ----------------------------------------------------------------------------- utilidades C#
def _cs_strip(src):
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    src = re.sub(r'@"(?:[^"]|"")*"', '""', src)
    src = re.sub(r'\$?"(?:\\.|[^"\\\n])*"', '""', src)
    src = re.sub(r"'(?:\\.|[^'\\])'", "' '", src)
    return src


def _cs_lines(src):
    return [re.sub(r"//.*", "", l) for l in _cs_strip(src).splitlines()]


def _method_body(src, name):
    clean = _cs_strip(re.sub(r"//[^\n]*", "", src))
    m = re.search(r"\bvoid\s+" + name + r"\s*\([^)]*\)\s*\{", clean)
    if not m:
        m2 = re.search(r"\bvoid\s+" + name + r"\s*\([^)]*\)\s*=>([^;]*);", clean)
        return m2.group(1) if m2 else ""
    i, depth = m.end() - 1, 0
    for j in range(i, len(clean)):
        if clean[j] == "{":
            depth += 1
        elif clean[j] == "}":
            depth -= 1
            if depth == 0:
                return clean[i:j + 1]
    return clean[i:]


def _member_lines(src):
    raw = src.splitlines()
    clean = _cs_lines(src)
    joined = "\n".join(clean)
    block_ns = bool(re.search(r"^\s*namespace\s+[\w.]+\s*(\{|$)", joined, re.M)) and \
        not re.search(r"^\s*namespace\s+[\w.]+\s*;", joined, re.M)
    member_depth = 2 if block_ns else 1
    depth, out = 0, []
    for idx, (r, c) in enumerate(zip(raw, clean)):
        if depth == member_depth:
            out.append((r, c, idx))
        depth += c.count("{") - c.count("}")
    return out, raw


_FIELD_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*(?P<mods>(?:(?:public|private|protected|internal|static|readonly|const|volatile|new)\s+)*)"
    r"(?P<type>[\w.]+(?:<[^;=()]*>)?(?:\[\])?\??)\s+(?P<name>[A-Za-z_]\w*)\s*(?:=(?!>)[^;]*)?;\s*$")


def unity_conventions(path, src):
    checks = {}
    folder = path.split("/")[2] if path.startswith("Assets/Scripts/") and path.count("/") >= 3 else None
    clean_all = "\n".join(_cs_lines(src))
    ns = re.search(r"^\s*namespace\s+([\w.]+)", clean_all, re.M)
    checks["namespace Game.<Carpeta>"] = bool(ns) and folder is not None and ns.group(1) == f"Game.{folder}"
    members, raw = _member_lines(src)
    public_fields, bad_private = [], []
    for r, c, _ in members:
        if "(" in c or "=>" in c or "{" in c:
            continue
        m = _FIELD_RE.match(c)
        if not m:
            continue
        mods = m.group("mods").split()
        if "const" in mods:
            continue
        if "public" in mods or "protected" in mods or "internal" in mods:
            public_fields.append(m.group("name"))
        elif "static" not in mods and not m.group("name").startswith("_"):
            bad_private.append(m.group("name"))
    checks["sin campos públicos"] = not public_fields
    checks["campos privados _camelCase"] = not bad_private
    undocumented = []
    for r, c, idx in members:
        if re.match(r"^\s*public\b", c) and not re.match(r"^\s*public\s+(const)\b", c):
            j = idx - 1
            while j >= 0 and re.match(r"^\s*\[", raw[j]):
                j -= 1
            if j < 0 or not raw[j].strip().startswith("///"):
                undocumented.append(c.strip()[:50])
    checks["docs /// en miembros públicos"] = not undocumented
    hot = "".join(_method_body(src, n) for n in ("Update", "FixedUpdate", "LateUpdate"))
    hot_bad = re.search(r"Find\w*Object|GameObject\.Find|GetComponent|\.(Where|Select|Any|First|ToList|ToArray|OrderBy)\s*\(|"
                        r"new\s+(List|Dictionary|HashSet|Queue|Stack)\s*<|new\s+\w+\s*\[", hot)
    checks["nada prohibido en Update"] = not hot_bad and "System.Linq" not in clean_all
    subs = re.findall(r"\.\s*(On\w+)\s*\+=", clean_all)
    if subs:
        en, dis = _method_body(src, "OnEnable"), _method_body(src, "OnDisable")
        checks["eventos += en OnEnable / -= en OnDisable"] = all(
            re.search(re.escape(s) + r"\s*\+=", en) and re.search(re.escape(s) + r"\s*-=", dis) for s in subs)
    checks["TryGetComponent (no GetComponent)"] = not re.search(r"\bGetComponent\s*[<(]", clean_all)
    checks["sin Debug.Log"] = not re.search(r"\bDebug\.Log", clean_all)
    return checks


def unity_balance(changed, task):
    allsrc = "\n".join(re.sub(r"//[^\n]*", "", v) for k, v in changed.items() if k.endswith(".cs"))
    c = {}
    if task == "T-103":
        eh = changed.get("Assets/Scripts/Enemies/EnemyHealth.cs", "")
        c["usa GameBalance.EnemyBaseHealth"] = "GameBalance.EnemyBaseHealth" in eh or (
            "EnemyBaseHealth" in eh and "using static Game.Utils.GameBalance" in eh)
        c["no usa LegacyBalance"] = "LegacyBalance" not in allsrc
    if task == "T-104":
        sp = re.sub(r"//[^\n]*", "", changed.get("Assets/Scripts/Enemies/EnemySpawner.cs", ""))
        c["usa GameBalance.EnemySpawnInterval"] = "EnemySpawnInterval" in sp and "GameBalance" in sp
        c["usa GameBalance.MaxAliveEnemies"] = "MaxAliveEnemies" in sp and "GameBalance" in sp
        c["no copia los números (1.75 / 4)"] = not re.search(r"\b1\.75f?\b", sp) and not re.search(r"[<>=]=?\s*4\b|\b4\s*[;)]", sp)
        c["no usa LegacyBalance"] = "LegacyBalance" not in allsrc
    return c


def _write_tree(root, files):
    for rel, txt in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8", newline="\n")


def snapshot(project, changed, deleted):
    files = dict(PROJECTS[project])
    for d in deleted:
        files.pop(d, None)
    files.update(changed)
    return files


def unity_tests(files, task):
    """Compila el proyecto + stubs + tests con dotnet y ejecuta los tests de comportamiento de la tarea."""
    sdk = _dotnet_sdk()
    if not sdk:
        return None, ["no hay SDK de .NET: no se pudieron ejecutar los tests de Unity"]
    exe, major = sdk
    work = Path(tempfile.gettempdir()) / "bench_agente_unity"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    (work / "src").mkdir(parents=True)
    _write_tree(work / "src", {k[len("Assets/Scripts/"):]: v for k, v in files.items()
                               if k.startswith("Assets/Scripts/") and k.endswith(".cs")})
    (work / "UnityStubs.cs").write_text(UNITY_STUBS, encoding="utf-8")
    (work / "Tests.cs").write_text(UNITY_TESTS_CS, encoding="utf-8")
    (work / "nuget.config").write_text('<?xml version="1.0" encoding="utf-8"?><configuration><packageSources><clear /></packageSources></configuration>', encoding="utf-8")
    (work / "Bench.csproj").write_text(f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net{major}.0</TargetFramework><UseAppHost>false</UseAppHost>
    <ImplicitUsings>disable</ImplicitUsings><Nullable>disable</Nullable><LangVersion>latest</LangVersion>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems><InvariantGlobalization>true</InvariantGlobalization>
    <SatelliteResourceLanguages>en</SatelliteResourceLanguages>
    <NoWarn>CS0618;CS0414;CS0169;CS0649;CS0067;CS8632;CS0108;CS0114</NoWarn>
  </PropertyGroup>
  <ItemGroup><Compile Include="src/**/*.cs" /><Compile Include="UnityStubs.cs" /><Compile Include="Tests.cs" /></ItemGroup>
</Project>""", encoding="utf-8")
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    b = subprocess.run([exe, "build", "-nologo", "-v", "q", "-clp:NoSummary"], cwd=work, capture_output=True,
                       text=True, env=env, timeout=300)
    if b.returncode != 0:
        errs = sorted({re.sub(r"^.*?[/\\]src[/\\]", "", l).strip() for l in (b.stdout + b.stderr).splitlines() if ": error " in l})
        return None, ["no compiló con los tests: " + "; ".join(errs[:3])]
    dll = work / "bin" / "Debug" / f"net{major}.0" / "Bench.dll"
    try:
        r = subprocess.run([exe, str(dll), task], cwd=work, capture_output=True, text=True, env=env, timeout=60)
    except subprocess.TimeoutExpired:
        return {"termina sin colgarse": False}, ["los tests no terminaron en 60 s (bucle infinito)"]
    m = re.search(r"@@RESULT@@(.*)", r.stdout)
    if not m:
        return None, ["sin resultado de tests: " + r.stderr[-300:]]
    data = json.loads(m.group(1))
    return {k: bool(v) for k, v in data["checks"].items()}, data.get("notes", [])


# ----------------------------------------------------------------------------- utilidades web
def _ts_nocomments(src):
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def web_conventions(src):
    code = _ts_nocomments(src)
    c = {
        "sin any": not re.search(r":\s*any\b|<any>|\bas\s+any\b|\bany\[\]|Array<any>", code),
        "sin @ts-ignore": "@ts-ignore" not in src and "@ts-expect-error" not in src,
        "sin var": not re.search(r"\bvar\s+\w", code),
        "sin export default": "export default" not in code,
        "sin console.log": not re.search(r"\bconsole\.(log|debug|info)\s*\(", code),
        "sin innerHTML con datos": not re.search(r"\.(outerHTML|insertAdjacentHTML)\b", code)
        and not re.search(r"\.innerHTML\s*\+?=(?!\s*[\"'`]{2}\s*[;\n])", code),
        "sin estilos en línea": not re.search(r"\.style\s*(\.|=|\[)|setAttribute\(\s*[\"']style", code),
    }
    lines = src.splitlines()
    undocumented = []
    for i, l in enumerate(lines):
        if re.match(r"^\s*export\s+(async\s+)?function\b|^\s*export\s+const\s+\w+\s*=\s*(async\s*)?\(", l):
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if j < 0 or not lines[j].strip().endswith("*/"):
                undocumented.append(l.strip()[:60])
    c["JSDoc en funciones exportadas"] = not undocumented
    return c


def web_config_checks(changed, task):
    c = {}
    if task == "W-203":
        src = _ts_nocomments(changed.get("src/api/products.ts", ""))
        c["usa API_LIMITS de config/limits"] = bool(re.search(r"from\s+[\"'][./]*config/limits[\"']", src)) and "API_LIMITS" in src
        c["no usa legacyLimits"] = "legacyLimits" not in src and "LEGACY_LIMITS" not in src
        c["no copia los límites (12 / 48)"] = not re.search(r"(?<![\w.])(12|48)(?![\w.])", src)
    return c


def _has(code, *pats):
    return all(re.search(p, code) for p in pats)


def web_static_tests(task, files):
    """Pruebas de comportamiento ESTIMADAS (sin Node.js): revisan en el código que cada requisito esté resuelto."""
    if task == "W-201":
        code = _ts_nocomments(files.get("src/lib/cart.ts", ""))
        add = re.search(r"function\s+addToCart.*?(?=\nexport\s|\Z)", code, re.S)
        add = add.group(0) if add else ""
        tot = re.search(r"function\s+cartTotals.*?(?=\nexport\s|\Z)", code, re.S)
        tot = tot.group(0) if tot else ""
        thr = re.search(r"[^;\n]*FREE_SHIPPING_THRESHOLD_CENTS[^;\n]*", tot)
        thr = thr.group(0) if thr else ""
        return {
            "addToCart no muta el carrito": not re.search(r"\.lines\.(push|splice|pop|shift|unshift)\(|\.quantity\s*(\+=|=(?!=))|\.lines\[[^\]]*\]\s*=(?!=)", add)
            and bool(re.search(r"\.\.\.|\.map\(|\.concat\(", add)),
            "mismo producto suma cantidad": bool(re.search(r"productId\s*===?|\.findIndex\(|\.find\(|\.some\(", add)),
            "rechaza cantidades no enteras / NaN": bool(re.search(r"Number\.is(Safe)?Integer\(", add)),
            "totales en centavos enteros": not re.search(r"(unitPriceCents|priceCents)\s*/\s*100", tot) and bool(re.search(r"Math\.round\(", tot)),
            "descuento solo sobre el subtotal": bool(re.search(r"(discount\w*|off\w*)\s*=\s*[^;]*subtotal", tot, re.I))
            and not re.search(r"discount\w*\s*=\s*[^;]*(gross|shipping)", tot, re.I),
            "envío según subtotal con descuento": bool(thr) and (bool(re.search(r"-\s*discount|after|discounted|net", thr, re.I)) or not re.search(r"\bsubtotal(Cents)?\b(?!\w)", thr)),
            "carrito vacío sin envío": bool(re.search(r"lines\.length\s*(===?\s*0|>\s*0)|!\s*cart\.lines\.length|subtotal\w*\s*(===?\s*0|>\s*0|<=\s*0)", tot)),
        }
    if task == "W-202":
        code = _ts_nocomments(files.get("src/ui/searchBox.ts", ""))
        return {
            "existe initSearchBox exportada": bool(re.search(r"export\s+function\s+initSearchBox\s*\(", code)),
            "debounce con setTimeout/clearTimeout": _has(code, r"setTimeout\(", r"clearTimeout\("),
            "debounce por defecto 300 ms": bool(re.search(r"\b300\b", code)),
            "recorta espacios (trim)": ".trim()" in code,
            "menos de 2 caracteres no busca": bool(re.search(r"length\s*<\s*2|length\s*<=\s*1|length\s*>=\s*2|MIN\w*\s*=\s*2", code)),
            "texto literal (textContent, sin HTML)": bool(re.search(r"\.textContent\s*=|createTextNode\(", code))
            and not re.search(r"\.innerHTML\s*\+?=(?!\s*[\"'`]{2}\s*[;\n])", code),
            "precio con 2 decimales": bool(re.search(r"toFixed\(\s*2\s*\)", code)),
            "estados 'Sin resultados' y 'Error al buscar'": "Sin resultados" in code and "Error al buscar" in code,
            "accesibilidad aria-controls y aria-live": "aria-controls" in code and "aria-live" in code and "polite" in code,
        }
    if task == "W-203":
        code = _ts_nocomments(files.get("src/api/products.ts", ""))
        return {
            "valida enteros (sin decimales ni texto)": bool(re.search(r"Number\.is(Safe)?Integer\(|/\^-?\\d\+\$/|/\^-?\[0-9\]\+\$/|/\^\[1-9\]|/\^\(0\|\[1-9\]", code)),
            "respuesta 400 INVALID_QUERY con field": _has(code, r"\b400\b", r"INVALID_QUERY", r"field"),
            "límite máximo de pageSize desde config": "maxPageSize" in code,
            "tamaño por defecto desde config": "defaultPageSize" in code,
            "calcula totalPages con Math.ceil": "Math.ceil(" in code,
            "pagina con slice": ".slice(" in code,
            "no muta los datos del repo": not re.search(r"repo\.all\(\)\s*\.(sort|reverse|splice)\(", code),
        }
    if task == "W-204":
        return w204_tests(files.get("public/contact.html", ""), files.get("public/css/contact.css", ""))
    return {}


class _Html(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.els = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        el = {"tag": tag, "attrs": dict(attrs), "parents": list(self.stack)}
        self.els.append(el)
        if tag not in ("input", "link", "meta", "br", "img", "hr"):
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.els.append({"tag": tag, "attrs": dict(attrs), "parents": list(self.stack)})

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break


def w204_tests(html_src, css):
    p = _Html()
    try:
        p.feed(html_src)
    except Exception:
        pass
    els = p.els
    by_id = {e["attrs"].get("id"): e for e in els if e["attrs"].get("id")}
    form = by_id.get("contact-form")
    in_form = [e for e in els if form and any(x is form for x in e["parents"])]

    def label_for(i):
        return any(e["tag"] == "label" and e["attrs"].get("for") == i for e in els) or \
            bool(by_id.get(i) and any(x["tag"] == "label" for x in by_id[i]["parents"]))
    classes = {c for e in els for c in (e["attrs"].get("class") or "").split()}
    bem = re.compile(r"^[a-z]+(-[a-z]+)*(__[a-z]+(-[a-z]+)*)?(--[a-z]+(-[a-z]+)*)?$")
    used = [c for c in classes if c.startswith("contact-form") and re.search(r"__|--", c)]
    hrefs = [e["attrs"].get("href") for e in els if e["tag"] == "link" and (e["attrs"].get("rel") or "") == "stylesheet"]
    fe = by_id.get("form-errors")
    return {
        "formulario conserva id, action y method": bool(form) and form["attrs"].get("action") == "/api/contact" and (form["attrs"].get("method") or "").lower() == "post",
        "campos conservan name": all(any(e["attrs"].get("name") == n for e in in_form) for n in ("name", "email", "message")),
        "cada campo tiene label asociado": all(label_for(i) for i in ("name", "email", "message")),
        "campos required y correo type=email": all(by_id.get(i) and "required" in by_id[i]["attrs"] for i in ("name", "email", "message"))
        and bool(by_id.get("email")) and by_id["email"]["attrs"].get("type") == "email",
        "botón real type=submit dentro del form": any(e["tag"] == "button" and e["attrs"].get("type") == "submit" for e in in_form),
        "sin JavaScript en línea": not any(k.startswith("on") for e in els for k in e["attrs"]),
        "#form-errors con aria-live=polite": bool(fe) and fe["attrs"].get("aria-live") == "polite",
        "sin estilos en línea": not any("style" in e["attrs"] for e in els) and not any(e["tag"] == "style" for e in els),
        "incluye contact.css y conserva site.css": "css/contact.css" in hrefs and "css/site.css" in hrefs,
        "contact.css define clases contact-form__*": bool(re.search(r"\.contact-form__[a-z]", css)),
        "clases BEM y definidas en el CSS": bool(classes) and all(bem.match(c) for c in classes) and bool(used)
        and all(re.search(r"\." + re.escape(c) + r"(?![\w-])", css) for c in used),
    }


_NODE_DEPS = Path(__file__).resolve().parent / "_deps_web"


def node_ready():
    node, npm = shutil.which("node"), shutil.which("npm") or shutil.which("npm.cmd")
    if not node or not npm:
        return None
    if not (_NODE_DEPS / "node_modules" / "jsdom").exists() or not (_NODE_DEPS / "node_modules" / "typescript").exists():
        print("  Node.js encontrado: instalando typescript y jsdom para las pruebas web reales (una sola vez)…")
        _NODE_DEPS.mkdir(exist_ok=True)
        r = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--prefix", str(_NODE_DEPS), "typescript@5.9.3", "jsdom@26"],
                           capture_output=True, text=True, timeout=600, shell=os.name == "nt")
        if r.returncode != 0:
            print("  no se pudo instalar (se usarán pruebas estimadas): " + r.stderr[-200:])
            return None
    (_NODE_DEPS / "run.js").write_text(WEB_TESTS_JS, encoding="utf-8")
    return node


def web_node_tests(node, files, task):
    work = _NODE_DEPS / "work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    _write_tree(work, {k: v for k, v in files.items() if k.startswith(("src/", "public/"))})
    (_NODE_DEPS / "tsconfig.json").write_text(TSCONFIG_JSON, encoding="utf-8")
    tsc = _NODE_DEPS / "node_modules" / "typescript" / "bin" / "tsc"
    t = subprocess.run([node, str(tsc), "-p", str(_NODE_DEPS / "tsconfig.json"), "--pretty", "false"], cwd=_NODE_DEPS,
                       capture_output=True, text=True, timeout=300)
    errors = [l.split("work/", 1)[-1].strip() for l in t.stdout.splitlines() if "error TS" in l]
    try:
        r = subprocess.run([node, str(_NODE_DEPS / "run.js"), task, str(work)], cwd=_NODE_DEPS, capture_output=True,
                           text=True, timeout=180)
        m = re.search(r"@@RESULT@@(.*)", r.stdout)
        data = json.loads(m.group(1)) if m else {"checks": {}, "notes": ["sin resultado"]}
    except subprocess.TimeoutExpired:
        data = {"checks": {"termina sin colgarse": False}, "notes": ["timeout"]}
    return errors, data["checks"], data["notes"]


def grade_run(task, changed, deleted, metrics, transcript, node=None):
    project = project_of(task)
    files = snapshot(project, changed, deleted)
    allowed = ALLOWED[task]
    out_of_scope = sorted(set(changed) - allowed) + [f"(borrado) {d}" for d in deleted]
    conv = {"solo tocó archivos permitidos": not out_of_scope,
            "creó/modificó lo pedido": all(a in changed for a in allowed)}
    touched = any(a in changed for a in allowed)
    notes, mode = [], ""
    tmp = Path(tempfile.gettempdir()) / "bench_agente_snap"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    _write_tree(tmp, files)
    build = run_build(tmp)
    compiles = build.startswith("Build OK")
    compile_errors = [] if compiles else build.splitlines()[1:4]
    if project == "unity":
        for p in sorted(changed):
            if p in allowed and p.endswith(".cs"):
                for k, v in unity_conventions(p, changed[p]).items():
                    conv[k] = conv.get(k, True) and v
        conv.update(unity_balance(changed, task))
        tests, notes = unity_tests(files, task) if compiles else (None, ["no compila"])
        if tests is None and compiles:
            compiles = False
            compile_errors = notes
        mode = "tests reales (dotnet)"
    else:
        for p in sorted(changed):
            if p in allowed and p.endswith(".ts"):
                for k, v in web_conventions(changed[p]).items():
                    conv[k] = conv.get(k, True) and v
        conv.update(web_config_checks(changed, task))
        if node:
            errors, tests, notes = web_node_tests(node, files, task)
            compiles = compiles and not errors
            compile_errors = compile_errors or errors[:3]
            mode = "tests reales (Node.js + tsc estricto)"
        else:
            tests = web_static_tests(task, files)
            mode = "tests estimados (sin Node.js)"
    tests = tests or {}
    func = (sum(tests.values()) / len(tests)) if (tests and touched and compiles) else 0.0
    if project == "web" and not node and touched and not compiles and tests:
        func = 0.5 * sum(tests.values()) / len(tests)  # el verificador estático es menos fiable: penaliza a la mitad
    convs = sum(conv.values()) / len(conv)
    used_build = any(c.get("function", {}).get("name") == "build" for m in transcript if m.get("role") == "assistant"
                     for c in (m.get("tool_calls") or []))
    return {"task": task, "compiles": compiles, "compile_errors": compile_errors, "tests": tests, "notes": notes,
            "mode": mode, "conventions": conv, "functional": round(func, 3), "convention": round(convs, 3),
            "out_of_scope": out_of_scope, "used_build": used_build, "metrics": metrics}

# ============================================================================= LENGUAJES ADICIONALES
# C++ general, Unreal C++ (con stubs del motor), Rust, .NET backend y JSON/Firebase.
import html as _html  # noqa: F401
import json as _json

EXTRA_PROJECTS = {"cpp": {"docs/CONVENTIONS.md": "# Convenciones C++ del proyecto\n\n- Estándar C++17. Todo el código vive en el namespace `bench`.\n- Encabezados con `#pragma once`. Nunca `using namespace std;` en un encabezado.\n- Prohibido `new`/`delete`/`malloc`/`free`: usa contenedores estándar o `std::unique_ptr`.\n- Miembros privados con prefijo `m_` (por ejemplo `m_items`).\n- Métodos que no modifican el objeto se declaran `const`.\n- Parámetros no triviales (strings, structs, contenedores) se pasan por `const&` o se mueven.\n- Un resultado que puede no existir se devuelve como `std::optional<T>`: nada de valores centinela\n  (ni `-1`, ni objetos vacíos, ni excepciones para el caso normal).\n- Sin `printf`/`std::cout` en el código de la biblioteca.\n- Los límites y valores de configuración vienen de `src/config.hpp` (no los copies como números).\n  `src/legacy/` está obsoleto: no lo uses.\n- Cada método público lleva comentario de documentación `///`.\n- El proyecto compila sin warnings con `-Wall -Wextra` (o `/W4` en MSVC).\n", "docs/tasks/CPP-301.md": "# CPP-301: Arreglar la cola de eventos\n\nArchivo: `src/event_queue.hpp` (puedes crear `src/event_queue.cpp` si separas la implementación;\nno modifiques ningún otro archivo).\n\nReportes del equipo:\n\n1. Fugas y crashes al destruir la cola (usa `new[]` con `delete`).\n2. Los eventos con la misma prioridad salen en desorden: deben salir en el orden en que llegaron (FIFO).\n3. Cuando la cola está llena (`config::kMaxQueuedEvents`), un evento nuevo **más prioritario** que el\n   menos prioritario de la cola debe entrar y expulsar a ese (si hay empate entre los menos prioritarios,\n   se expulsa el que llegó último). Si no es más prioritario, se rechaza. `push` devuelve si entró.\n4. Las prioridades fuera de `[config::kMinPriority, config::kMaxPriority]` se rechazan (`push` devuelve false).\n5. `pop()` en una cola vacía devuelve un evento vacío que se confunde con uno real: debe devolver\n   `std::optional<Event>` vacío.\n6. `size()` no se puede llamar sobre una cola `const` y devuelve `int`: debe ser `std::size_t` y `const`.\n7. `drainUntil(t)` debe devolver, en orden de prioridad (y FIFO en empates), **todos** los eventos con\n   `time <= t`, aunque haya eventos más prioritarios con `time > t` (esos se quedan en la cola).\n\nMantén los nombres `bench::Event` (campos `name`, `priority`, `time`) y `bench::EventQueue`\n(métodos `push`, `pop`, `size`, `drainUntil`) y cumple `docs/CONVENTIONS.md`.\n", "src/config.hpp": "#pragma once\n#include <cstddef>\n\nnamespace bench::config {\n\n/// Máximo de eventos que puede tener encolados la EventQueue.\nconstexpr std::size_t kMaxQueuedEvents = 8;\n\n/// Prioridad mínima válida de un evento.\nconstexpr int kMinPriority = 0;\n\n/// Prioridad máxima válida de un evento.\nconstexpr int kMaxPriority = 10;\n\n}  // namespace bench::config\n", "src/event_queue.hpp": "#pragma once\n#include <algorithm>\n#include <string>\n#include <vector>\n#include \"legacy/old_config.hpp\"\n\nusing namespace std;\n\nnamespace bench {\n\n/// Evento del juego que se procesa por prioridad.\nstruct Event {\n    string name;\n    int priority = 0;   // 0..10, mayor = más urgente\n    double time = 0.0;  // segundo de juego en el que debe procesarse\n};\n\n/// Cola de eventos del juego. Ver docs/tasks/CPP-301.md.\nclass EventQueue {\npublic:\n    EventQueue() { items = new Event[MAX_EVENTS]; }\n    ~EventQueue() { delete items; }\n\n    /// Encola un evento.\n    bool push(Event e) {\n        if (count >= MAX_EVENTS) return false;\n        items[count++] = e;\n        std::sort(items, items + count, [](const Event& a, const Event& b) { return a.priority > b.priority; });\n        return true;\n    }\n\n    /// Saca el evento más prioritario.\n    Event pop() {\n        if (count == 0) return Event{};\n        Event top = items[0];\n        for (int i = 1; i < count; ++i) items[i - 1] = items[i];\n        --count;\n        return top;\n    }\n\n    /// Cantidad de eventos encolados.\n    int size() { return count; }\n\n    /// Saca todos los eventos con time <= t.\n    vector<Event> drainUntil(double t) {\n        vector<Event> out;\n        while (count > 0 && items[0].time <= t) out.push_back(pop());\n        return out;\n    }\n\nprivate:\n    Event* items;\n    int count = 0;\n};\n\n}  // namespace bench\n", "src/legacy/old_config.hpp": "#pragma once\n// OBSOLETO: valores de la versión 1 del motor. No usar en código nuevo.\n#define MAX_EVENTS 16\n#define MAX_PRIORITY 5\n", "src/main.cpp": "#include \"event_queue.hpp\"\n\n// Punto de entrada mínimo para verificar que el proyecto compila.\nint main() {\n    bench::EventQueue queue;\n    queue.push({\"spawn\", 3, 0.5});\n    return 0;\n}\n", "src/util/math.hpp": "#pragma once\n\nnamespace bench::util {\n\n/// Limita `value` al rango [lo, hi].\ntemplate <typename T>\nconstexpr T clamp(T value, T lo, T hi) {\n    return value < lo ? lo : (hi < value ? hi : value);\n}\n\n}  // namespace bench::util\n", "src/util/strings.hpp": "#pragma once\n#include <string>\n#include <string_view>\n\nnamespace bench::util {\n\n/// Devuelve true si `text` empieza con `prefix`.\ninline bool startsWith(std::string_view text, std::string_view prefix) {\n    return text.substr(0, prefix.size()) == prefix;\n}\n\n/// Quita espacios al inicio y al final.\ninline std::string trim(std::string_view text) {\n    const auto first = text.find_first_not_of(\" \\t\\r\\n\");\n    if (first == std::string_view::npos) return {};\n    const auto last = text.find_last_not_of(\" \\t\\r\\n\");\n    return std::string(text.substr(first, last - first + 1));\n}\n\n}  // namespace bench::util\n"}, "unreal": {"Source/Arena/Characters/ArenaCharacter.cpp": "#include \"ArenaCharacter.h\"\n#include \"Components/HealthComponent.h\"\n\nAArenaCharacter::AArenaCharacter()\n{\n\tHealthComponent = NewObject<UHealthComponent>(this);\n\tHealthComponent->SetOwnerForTests(this);\n}\n\nvoid AArenaCharacter::BeginPlay()\n{\n\tAActor::BeginPlay();\n\tHealthComponent->OnHealthChanged.AddDynamic(this, &AArenaCharacter::HandleHealthChanged);\n\tHealthComponent->OnDeath.AddDynamic(this, &AArenaCharacter::HandleDeath);\n\tstatic_cast<UActorComponent*>(HealthComponent)->BeginPlay();\n}\n\nvoid AArenaCharacter::HandleHealthChanged(float NewHealth, float Delta)\n{\n\t(void)NewHealth;\n\t(void)Delta;\n\t++HudUpdates;\n}\n\nvoid AArenaCharacter::HandleDeath()\n{\n\tbIsDowned = true;\n}\n", "Source/Arena/Characters/ArenaCharacter.h": "#pragma once\n\n#include \"CoreMinimal.h\"\n#include \"GameFramework/Actor.h\"\n#include \"ArenaCharacter.generated.h\"\n\nclass UHealthComponent;\n\n/** Personaje jugable del modo Arena. */\nUCLASS()\nclass ARENA_API AArenaCharacter : public AActor\n{\n\tGENERATED_BODY()\n\npublic:\n\tAArenaCharacter();\n\n\tvirtual void BeginPlay() override;\n\n\t/** Componente de vida del personaje. */\n\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = \"Arena\")\n\tUHealthComponent* HealthComponent = nullptr;\n\n\t/** Veces que el HUD fue notificado (lo usa el HUD de depuración). */\n\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = \"Arena\")\n\tint32 HudUpdates = 0;\n\n\t/** true cuando el personaje murió. */\n\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = \"Arena\")\n\tbool bIsDowned = false;\n\nprotected:\n\tUFUNCTION()\n\tvoid HandleHealthChanged(float NewHealth, float Delta);\n\n\tUFUNCTION()\n\tvoid HandleDeath();\n};\n", "Source/Arena/Config/ArenaBalance.h": "#pragma once\n\n/** Valores de balance vigentes del modo Arena (los ajusta diseño). */\nnamespace ArenaBalance\n{\n\t/** Vida máxima por defecto de personajes y enemigos. */\n\tconstexpr float DefaultMaxHealth = 150.f;\n\n\t/** Vida regenerada por segundo. */\n\tconstexpr float RegenPerSecond = 5.f;\n\n\t/** Segundos sin recibir daño antes de empezar a regenerar. */\n\tconstexpr float RegenDelaySeconds = 3.f;\n}\n", "Source/Arena/Config/LegacyBalance.h": "#pragma once\n\n// OBSOLETO: balance de la versión anterior del juego. No usar en código nuevo.\n#define LEGACY_MAX_HEALTH 100.f\n#define LEGACY_REGEN 10.f\n", "Source/Arena/Pickups/HealthPickup.cpp": "#include \"HealthPickup.h\"\n#include \"Characters/ArenaCharacter.h\"\n#include \"Components/HealthComponent.h\"\n\nvoid AHealthPickup::Consume(AArenaCharacter* Character)\n{\n\tif (!IsValid(Character) || !IsValid(Character->HealthComponent))\n\t{\n\t\treturn;\n\t}\n\tif (Character->HealthComponent->Heal(HealAmount))\n\t{\n\t\tDestroy();\n\t}\n}\n", "Source/Arena/Pickups/HealthPickup.h": "#pragma once\n\n#include \"CoreMinimal.h\"\n#include \"GameFramework/Actor.h\"\n#include \"HealthPickup.generated.h\"\n\nclass AArenaCharacter;\n\n/** Botiquín que cura al personaje que lo recoge. */\nUCLASS()\nclass ARENA_API AHealthPickup : public AActor\n{\n\tGENERATED_BODY()\n\npublic:\n\t/** Vida que cura este botiquín. */\n\tUPROPERTY(EditAnywhere, BlueprintReadOnly, Category = \"Pickup\")\n\tfloat HealAmount = 40.f;\n\n\t/** Aplica la curación al personaje y destruye el botiquín. */\n\tUFUNCTION(BlueprintCallable, Category = \"Pickup\")\n\tvoid Consume(AArenaCharacter* Character);\n};\n", "ThirdParty/UnrealStubs/Components/ActorComponent.h": "#pragma once\n#include \"CoreMinimal.h\"\n#include \"GameFramework/Actor.h\"\n\nenum ELevelTick { LEVELTICK_TimeOnly = 0, LEVELTICK_ViewportsOnly = 1, LEVELTICK_All = 2, LEVELTICK_PauseTick = 3 };\n\nstruct FActorComponentTickFunction {\n    bool bCanEverTick = false;\n    bool bStartWithTickEnabled = true;\n};\n\nclass UActorComponent : public UObject {\npublic:\n    virtual ~UActorComponent() = default;\n    virtual void BeginPlay() {}\n    virtual void EndPlay() {}\n    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) {\n        (void)DeltaTime; (void)TickType; (void)ThisTickFunction;\n    }\n    AActor* GetOwner() const { return Owner; }\n    void SetOwnerForTests(AActor* InOwner) { Owner = InOwner; }\n    FActorComponentTickFunction PrimaryComponentTick;\nprivate:\n    AActor* Owner = nullptr;\n};\n", "ThirdParty/UnrealStubs/CoreMinimal.h": "// Stubs mínimos de Unreal Engine para compilar y probar fuera del editor.\n// Reproducen la API usada en el proyecto (macros de reflexión vacías, tipos básicos, delegados).\n#pragma once\n#include <algorithm>\n#include <cmath>\n#include <cstdint>\n#include <cstdio>\n#include <functional>\n#include <memory>\n#include <string>\n#include <utility>\n#include <vector>\n\nusing int32 = std::int32_t;\nusing uint8 = std::uint8_t;\nusing uint32 = std::uint32_t;\nusing int64 = std::int64_t;\n\n#define UCLASS(...)\n#define USTRUCT(...)\n#define UENUM(...)\n#define UPROPERTY(...)\n#define UFUNCTION(...)\n#define UMETA(...)\n#define GENERATED_BODY()\n#define GENERATED_UCLASS_BODY()\n#define ARENA_API\n#define TEXT(x) x\n#define check(x) ((void)0)\n#define ensure(x) (x)\n#define ensureMsgf(x, ...) (x)\n#define UE_LOG(Category, Verbosity, ...) ((void)0)\n#define DECLARE_LOG_CATEGORY_EXTERN(...)\n#define DEFINE_LOG_CATEGORY(...)\n\nclass FString : public std::string {\npublic:\n    using std::string::string;\n    FString() = default;\n    FString(const std::string& s) : std::string(s) {}\n    int32 Len() const { return static_cast<int32>(size()); }\n    bool IsEmpty() const { return empty(); }\n    const char* operator*() const { return c_str(); }\n};\n\nclass FName : public FString {\npublic:\n    using FString::FString;\n    FName() = default;\n};\n\ntemplate <typename T>\nclass TArray {\npublic:\n    TArray() = default;\n    TArray(std::initializer_list<T> init) : Data(init) {}\n    int32 Add(const T& v) { Data.push_back(v); return Num() - 1; }\n    int32 Num() const { return static_cast<int32>(Data.size()); }\n    bool IsValidIndex(int32 i) const { return i >= 0 && i < Num(); }\n    void RemoveAt(int32 i) { Data.erase(Data.begin() + i); }\n    int32 Remove(const T& v) { auto n = Data.size(); Data.erase(std::remove(Data.begin(), Data.end(), v), Data.end()); return static_cast<int32>(n - Data.size()); }\n    bool Contains(const T& v) const { return std::find(Data.begin(), Data.end(), v) != Data.end(); }\n    void Empty() { Data.clear(); }\n    T& operator[](int32 i) { return Data[static_cast<size_t>(i)]; }\n    const T& operator[](int32 i) const { return Data[static_cast<size_t>(i)]; }\n    auto begin() { return Data.begin(); }\n    auto end() { return Data.end(); }\n    auto begin() const { return Data.begin(); }\n    auto end() const { return Data.end(); }\nprivate:\n    std::vector<T> Data;\n};\n\nstruct FVector {\n    float X = 0.f, Y = 0.f, Z = 0.f;\n    FVector() = default;\n    FVector(float InX, float InY, float InZ) : X(InX), Y(InY), Z(InZ) {}\n    static float Dist(const FVector& A, const FVector& B) {\n        return std::sqrt((A.X - B.X) * (A.X - B.X) + (A.Y - B.Y) * (A.Y - B.Y) + (A.Z - B.Z) * (A.Z - B.Z));\n    }\n};\n\nstruct FMath {\n    template <typename T> static T Clamp(T V, T Lo, T Hi) { return V < Lo ? Lo : (Hi < V ? Hi : V); }\n    template <typename T> static T Max(T A, T B) { return A < B ? B : A; }\n    template <typename T> static T Min(T A, T B) { return A < B ? A : B; }\n    static bool IsNearlyZero(float V, float Tol = 1.e-4f) { return std::fabs(V) <= Tol; }\n    static bool IsNearlyEqual(float A, float B, float Tol = 1.e-4f) { return std::fabs(A - B) <= Tol; }\n};\n\nclass UObject {\npublic:\n    virtual ~UObject() = default;\n    FString GetName() const { return Name; }\n    FString Name = \"Object\";\n};\n\ninline bool IsValid(const UObject* Obj) { return Obj != nullptr; }\n\ntemplate <typename T, typename... Args>\nT* NewObject(UObject* Outer = nullptr, Args&&... args) {\n    (void)Outer;\n    static std::vector<std::unique_ptr<UObject>> Pool;\n    Pool.emplace_back(new T(std::forward<Args>(args)...));\n    return static_cast<T*>(Pool.back().get());\n}\n\n// ---- Delegados dinámicos multicast (AddDynamic / RemoveDynamic / Broadcast) ----\ntemplate <typename... Args>\nclass TMulticastDelegateStub {\npublic:\n    template <typename UserClass>\n    void __Internal_AddDynamic(UserClass* Obj, void (UserClass::*Func)(Args...)) {\n        Bindings.push_back({static_cast<void*>(Obj), [Obj, Func](Args... a) { (Obj->*Func)(a...); }});\n    }\n    template <typename UserClass>\n    void __Internal_RemoveDynamic(UserClass* Obj, void (UserClass::*)(Args...)) {\n        Bindings.erase(std::remove_if(Bindings.begin(), Bindings.end(), [Obj](const Binding& b) { return b.Owner == Obj; }), Bindings.end());\n    }\n    void Broadcast(Args... a) const { auto Copy = Bindings; for (auto& b : Copy) b.Call(a...); }\n    bool IsBound() const { return !Bindings.empty(); }\n    void Clear() { Bindings.clear(); }\nprivate:\n    struct Binding { void* Owner; std::function<void(Args...)> Call; };\n    std::vector<Binding> Bindings;\n};\n\n#define AddDynamic(Obj, Func) __Internal_AddDynamic(Obj, Func)\n#define RemoveDynamic(Obj, Func) __Internal_RemoveDynamic(Obj, Func)\n#define DECLARE_DYNAMIC_MULTICAST_DELEGATE(Name) using Name = TMulticastDelegateStub<>;\n#define DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(Name, T1, N1) using Name = TMulticastDelegateStub<T1>;\n#define DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(Name, T1, N1, T2, N2) using Name = TMulticastDelegateStub<T1, T2>;\n#define DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(Name, T1, N1, T2, N2, T3, N3) using Name = TMulticastDelegateStub<T1, T2, T3>;\n", "ThirdParty/UnrealStubs/GameFramework/Actor.h": "#pragma once\n#include \"CoreMinimal.h\"\n\nclass UActorComponent;\n\nclass AActor : public UObject {\npublic:\n    virtual void BeginPlay() {}\n    virtual void Tick(float DeltaSeconds) { (void)DeltaSeconds; }\n    void Destroy() { bPendingKill = true; }\n    bool IsPendingKill() const { return bPendingKill; }\n    FVector GetActorLocation() const { return Location; }\n    void SetActorLocation(const FVector& L) { Location = L; }\n    FVector Location;\n    bool bPendingKill = false;\n};\n", "docs/CONVENTIONS.md": "# Convenciones Unreal C++ (módulo Arena)\n\nSigue el estándar de código de Epic:\n\n- Prefijos de tipo: `U` (UObject/componentes), `A` (actores), `F` (structs), `E` (enums), `I` (interfaces).\n  Booleanos con prefijo `b` (`bIsDead`). Nombres en PascalCase, sin snake_case.\n- Clases reflejadas: `UCLASS(...)` + `GENERATED_BODY()`. El `#include \"<Archivo>.generated.h\"` es el\n  **último** include del encabezado.\n- Componentes que se agregan desde Blueprint: `UCLASS(ClassGroup = (Arena), meta = (BlueprintSpawnableComponent))`.\n- Todo miembro expuesto lleva `UPROPERTY(...)` con `Category`. Valores ajustables por diseño:\n  `EditAnywhere, BlueprintReadOnly`. Estado de solo lectura: `VisibleAnywhere, BlueprintReadOnly`.\n- Funciones para Blueprint: `UFUNCTION(BlueprintCallable, Category = ...)`; consultas sin efectos:\n  `UFUNCTION(BlueprintPure, Category = ...)` y `const`.\n- Eventos: `DECLARE_DYNAMIC_MULTICAST_DELEGATE_*` (nombre `FOn...`) y propiedad\n  `UPROPERTY(BlueprintAssignable, Category = ...)`.\n- Contenedores y utilidades de Unreal: `TArray`, `FString`, `FMath::Clamp`… Nada de `std::vector`,\n  `std::string`, `std::cout`, `printf`, `new`/`delete`.\n- Los valores de balance vienen de `Source/Arena/Config/ArenaBalance.h` (no copies los números).\n  `LegacyBalance.h` está obsoleto.\n- Comentario de documentación `/** ... */` en cada miembro público.\n- Los encabezados empiezan con `#pragma once`. Tabs para indentar.\n", "docs/tasks/UE-302.md": "# UE-302: Componente de vida (UHealthComponent)\n\nCrear:\n- `Source/Arena/Components/HealthComponent.h`\n- `Source/Arena/Components/HealthComponent.cpp`\n\n(no modifiques ningún otro archivo; `ArenaCharacter` y `HealthPickup` ya lo usan).\n\nRequisitos:\n\n1. `UHealthComponent` hereda de `UActorComponent` y se puede agregar desde Blueprint.\n2. Propiedades: `MaxHealth` (ajustable por diseño, por defecto el valor vigente de balance) y\n   `CurrentHealth` (solo lectura). En `BeginPlay`, `CurrentHealth = MaxHealth`.\n3. Eventos para Blueprint:\n   - `OnHealthChanged(float NewHealth, float Delta)` — tipo `FOnHealthChanged`.\n   - `OnDeath()` — tipo `FOnDeath`, se emite **una sola vez**.\n4. `bool ApplyDamage(float Amount)`: ignora cantidades `<= 0` y daño a un componente muerto\n   (devuelve false). Nunca baja de 0. Emite `OnHealthChanged` con `Delta` negativo. Al llegar a 0\n   queda muerto (`IsDead()`) y emite `OnDeath`.\n5. `bool Heal(float Amount)`: ignora `<= 0`, no cura a un muerto, no pasa de `MaxHealth`. Si la vida\n   ya está llena no hace nada y devuelve false. Emite `OnHealthChanged` con `Delta` positivo.\n6. Consulta para Blueprint: `bool IsDead() const`.\n\nCumple `docs/CONVENTIONS.md`.\n"}, "rust": {"Cargo.lock": "# This file is automatically @generated by Cargo.\n# It is not intended for manual editing.\nversion = 4\n\n[[package]]\nname = \"savegame\"\nversion = \"0.1.0\"\n", "Cargo.toml": "[package]\nname = \"savegame\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\n", "docs/CONVENTIONS.md": "# Convenciones Rust\n\n- Edición 2021, sin dependencias externas.\n- En código que no es de test: prohibido `unwrap()`, `expect()`, `panic!`, `todo!`, `unimplemented!` y\n  `unsafe`. Los errores se propagan con `Result` y `?`.\n- Los límites vienen de `src/config.rs` (no copies los números). `src/legacy.rs` está obsoleto.\n- Todo ítem `pub` lleva comentario de documentación `///`.\n- `cargo build` sin warnings. Código idiomático (que `cargo clippy` no se queje si está disponible).\n- No cambies los tipos públicos existentes (`SaveData`, `SaveError`) ni las firmas de las funciones.\n", "docs/tasks/RS-401.md": "# RS-401: Leer partidas guardadas\n\nArchivo: `src/save.rs` (no modifiques ningún otro archivo). Implementa `parse_save`\n(`to_save_string` ya está hecho y debe cumplirse que `parse_save(&to_save_string(&d)) == Ok(d)`).\n\nFormato (una entrada por línea):\n\n```\n# comentario\nversion=2\nplayer=Rodrigo\ngold=1500\nitem=potion:3\nitem=sword:1\n```\n\nReglas de `parse_save`:\n- Se ignoran líneas vacías, líneas que empiezan con `#` y los espacios alrededor de claves y valores.\n- Una línea sin `=` → `SaveError::Malformed { line }`. Clave desconocida → `UnknownKey { line, key }`.\n  `line` es el número de línea real del texto (empezando en 1).\n- `version` es obligatoria (`MissingField(\"version\")`) y debe ser la versión soportada; si no,\n  `UnsupportedVersion(n)`. `player` es obligatorio y no puede quedar vacío (`MissingField(\"player\")`).\n- `gold` es opcional (0 por defecto). Números que no sean enteros válidos (`u32`) → `InvalidNumber { line, value }`.\n- `item=nombre:cantidad`: cantidad de 1 en adelante (si no → `InvalidNumber`). Si el mismo objeto\n  aparece varias veces se suman; si la suma pasa el máximo de pila → `StackOverflow { item }`.\n\nCumple `docs/CONVENTIONS.md`.\n", "src/config.rs": "//! Límites vigentes del formato de guardado.\n\n/// Versión del formato de guardado que se soporta.\npub const SAVE_VERSION: u32 = 2;\n\n/// Máximo de unidades de un mismo objeto en una casilla.\npub const MAX_STACK: u32 = 99;\n\n/// Máximo de objetos distintos en el inventario.\npub const MAX_SLOTS: usize = 20;\n", "src/inventory.rs": "//! Inventario en memoria.\n\nuse std::collections::BTreeMap;\n\nuse crate::config::{MAX_SLOTS, MAX_STACK};\n\n/// Error al modificar el inventario.\n#[derive(Debug, Clone, PartialEq, Eq)]\npub enum InventoryError {\n    /// No caben más objetos distintos.\n    Full,\n    /// La pila superaría el máximo.\n    StackLimit,\n}\n\n/// Inventario: nombre de objeto → cantidad.\n#[derive(Debug, Default, Clone, PartialEq, Eq)]\npub struct Inventory {\n    items: BTreeMap<String, u32>,\n}\n\nimpl Inventory {\n    /// Agrega `qty` unidades de `name`.\n    pub fn add(&mut self, name: &str, qty: u32) -> Result<(), InventoryError> {\n        let current = self.items.get(name).copied().unwrap_or(0);\n        if current == 0 && self.items.len() >= MAX_SLOTS {\n            return Err(InventoryError::Full);\n        }\n        if current + qty > MAX_STACK {\n            return Err(InventoryError::StackLimit);\n        }\n        self.items.insert(name.to_string(), current + qty);\n        Ok(())\n    }\n\n    /// Cantidad de `name` (0 si no hay).\n    pub fn count(&self, name: &str) -> u32 {\n        self.items.get(name).copied().unwrap_or(0)\n    }\n}\n", "src/legacy.rs": "//! Valores del formato v1. Obsoletos: no usar en código nuevo.\n\n/// Tamaño de pila del formato v1.\n#[deprecated(note = \"usa config::MAX_STACK\")]\npub const OLD_MAX_STACK: u32 = 64;\n", "src/lib.rs": "//! Utilidades de partidas guardadas del juego.\n\npub mod config;\npub mod inventory;\npub mod legacy;\npub mod save;\n\npub use save::{parse_save, to_save_string, SaveData, SaveError};\n", "src/save.rs": "//! Lectura y escritura del archivo de partida (formato texto `clave=valor`).\n\nuse std::collections::BTreeMap;\nuse std::fmt;\n\n/// Datos de una partida guardada.\n#[derive(Debug, Clone, PartialEq, Eq, Default)]\npub struct SaveData {\n    /// Versión del formato.\n    pub version: u32,\n    /// Nombre del jugador.\n    pub player: String,\n    /// Oro del jugador.\n    pub gold: u32,\n    /// Objetos: nombre → cantidad.\n    pub items: BTreeMap<String, u32>,\n}\n\n/// Errores al leer una partida. `line` es el número de línea (empezando en 1).\n#[derive(Debug, Clone, PartialEq, Eq)]\npub enum SaveError {\n    /// Línea sin `=`.\n    Malformed { line: usize },\n    /// Clave desconocida.\n    UnknownKey { line: usize, key: String },\n    /// Número inválido (no numérico, negativo, fuera de rango o cantidad 0).\n    InvalidNumber { line: usize, value: String },\n    /// Falta un campo obligatorio (`\"version\"` o `\"player\"`).\n    MissingField(&'static str),\n    /// Versión distinta de la soportada.\n    UnsupportedVersion(u32),\n    /// Un objeto supera el tamaño máximo de pila (sumando todas sus líneas).\n    StackOverflow { item: String },\n}\n\nimpl fmt::Display for SaveError {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        match self {\n            SaveError::Malformed { line } => write!(f, \"línea {line}: falta '='\"),\n            SaveError::UnknownKey { line, key } => write!(f, \"línea {line}: clave desconocida '{key}'\"),\n            SaveError::InvalidNumber { line, value } => write!(f, \"línea {line}: número inválido '{value}'\"),\n            SaveError::MissingField(name) => write!(f, \"falta el campo '{name}'\"),\n            SaveError::UnsupportedVersion(v) => write!(f, \"versión {v} no soportada\"),\n            SaveError::StackOverflow { item } => write!(f, \"demasiadas unidades de '{item}'\"),\n        }\n    }\n}\n\nimpl std::error::Error for SaveError {}\n\n/// Lee una partida. Ver docs/tasks/RS-401.md.\npub fn parse_save(input: &str) -> Result<SaveData, SaveError> {\n    todo!(\"RS-401: implementar parse_save ({} bytes)\", input.len())\n}\n\n/// Escribe una partida en el formato de texto (ya implementado).\npub fn to_save_string(data: &SaveData) -> String {\n    let mut out = format!(\"version={}\\nplayer={}\\ngold={}\\n\", data.version, data.player, data.gold);\n    for (name, qty) in &data.items {\n        out.push_str(&format!(\"item={name}:{qty}\\n\"));\n    }\n    out\n}\n"}, "dotnet": {"AppBuilder.cs": "using Leaderboard.Api.Domain;\nusing Leaderboard.Api.Endpoints;\nusing Leaderboard.Api.Infrastructure;\nusing Leaderboard.Api.Options;\n\nnamespace Leaderboard.Api;\n\n/// <summary>Construye la aplicación (lo usan Program.cs y los tests de integración).</summary>\npublic static class AppBuilder\n{\n    /// <summary>Crea la WebApplication con servicios y endpoints registrados.</summary>\n    public static WebApplication Build(string[] args)\n    {\n        var builder = WebApplication.CreateBuilder(args);\n        builder.Services.Configure<LeaderboardOptions>(builder.Configuration.GetSection(LeaderboardOptions.SectionName));\n        builder.Services.AddSingleton<IScoreRepository, InMemoryScoreRepository>();\n        builder.Services.AddProblemDetails();\n\n        var app = builder.Build();\n        app.MapScoreEndpoints();\n        return app;\n    }\n}\n", "Contracts/ScoreContracts.cs": "namespace Leaderboard.Api.Contracts;\n\n/// <summary>Cuerpo de POST /api/scores.</summary>\n/// <param name=\"PlayerId\">Id del jugador.</param>\n/// <param name=\"Score\">Puntaje enviado.</param>\npublic sealed record SubmitScoreRequest(string? PlayerId, int? Score);\n\n/// <summary>Posición de un jugador en el leaderboard.</summary>\n/// <param name=\"PlayerId\">Id del jugador.</param>\n/// <param name=\"Score\">Mejor puntaje.</param>\n/// <param name=\"Rank\">Posición (1 = primero).</param>\npublic sealed record ScoreResponse(string PlayerId, int Score, int Rank);\n", "Domain/IScoreRepository.cs": "namespace Leaderboard.Api.Domain;\n\n/// <summary>Almacenamiento de puntajes.</summary>\npublic interface IScoreRepository\n{\n    /// <summary>Guarda el puntaje si es el mejor del jugador. Devuelve la entrada vigente del jugador.</summary>\n    Task<ScoreEntry> SubmitAsync(string playerId, int score, CancellationToken cancellationToken);\n\n    /// <summary>Todas las entradas (sin orden garantizado).</summary>\n    Task<IReadOnlyList<ScoreEntry>> GetAllAsync(CancellationToken cancellationToken);\n\n    /// <summary>Entrada de un jugador o null.</summary>\n    Task<ScoreEntry?> FindAsync(string playerId, CancellationToken cancellationToken);\n}\n", "Domain/ScoreEntry.cs": "namespace Leaderboard.Api.Domain;\n\n/// <summary>Mejor puntaje registrado de un jugador.</summary>\n/// <param name=\"PlayerId\">Id del jugador.</param>\n/// <param name=\"Score\">Mejor puntaje.</param>\n/// <param name=\"Sequence\">Orden en que se logró ese puntaje (para desempatar: menor = antes).</param>\npublic sealed record ScoreEntry(string PlayerId, int Score, long Sequence);\n", "Endpoints/ScoreEndpoints.cs": "using Leaderboard.Api.Domain;\n\nnamespace Leaderboard.Api.Endpoints;\n\n/// <summary>Endpoints de /api/scores. Ver docs/tasks/NET-501.md.</summary>\npublic static class ScoreEndpoints\n{\n    /// <summary>Registra los endpoints.</summary>\n    public static IEndpointRouteBuilder MapScoreEndpoints(this IEndpointRouteBuilder app)\n    {\n        app.MapGet(\"/api/scores\", async (IScoreRepository repo, CancellationToken ct) =>\n        {\n            var all = await repo.GetAllAsync(ct);\n            return Results.Ok(all);\n        });\n        return app;\n    }\n}\n", "Infrastructure/InMemoryScoreRepository.cs": "using Leaderboard.Api.Domain;\n\nnamespace Leaderboard.Api.Infrastructure;\n\n/// <summary>Repositorio en memoria.</summary>\npublic sealed class InMemoryScoreRepository : IScoreRepository\n{\n    private readonly Dictionary<string, ScoreEntry> _entries = new();\n    private long _sequence;\n\n    /// <inheritdoc />\n    public Task<ScoreEntry> SubmitAsync(string playerId, int score, CancellationToken cancellationToken)\n    {\n        _sequence++;\n        var entry = new ScoreEntry(playerId, score, _sequence);\n        _entries[playerId] = entry;\n        return Task.FromResult(entry);\n    }\n\n    /// <inheritdoc />\n    public Task<IReadOnlyList<ScoreEntry>> GetAllAsync(CancellationToken cancellationToken) =>\n        Task.FromResult<IReadOnlyList<ScoreEntry>>(_entries.Values.ToList());\n\n    /// <inheritdoc />\n    public Task<ScoreEntry?> FindAsync(string playerId, CancellationToken cancellationToken) =>\n        Task.FromResult(_entries.TryGetValue(playerId, out var e) ? e : null);\n}\n", "Leaderboard.Api.csproj": "<Project Sdk=\"Microsoft.NET.Sdk.Web\">\n  <PropertyGroup>\n    <TargetFramework>net8.0</TargetFramework>\n    <Nullable>enable</Nullable>\n    <ImplicitUsings>enable</ImplicitUsings>\n    <RootNamespace>Leaderboard.Api</RootNamespace>\n  </PropertyGroup>\n</Project>\n", "Legacy/OldLimits.cs": "namespace Leaderboard.Api.Legacy;\n\n/// <summary>OBSOLETO: límites de la API v1. No usar.</summary>\n[Obsolete(\"Usa LeaderboardOptions\")]\npublic static class OldLimits\n{\n    /// <summary>Top de la v1.</summary>\n    public const int Top = 100;\n\n    /// <summary>Puntaje máximo de la v1.</summary>\n    public const int MaxScore = 99999;\n}\n", "Options/LeaderboardOptions.cs": "namespace Leaderboard.Api.Options;\n\n/// <summary>Límites vigentes del leaderboard (sección \"Leaderboard\" de appsettings.json).</summary>\npublic sealed class LeaderboardOptions\n{\n    /// <summary>Nombre de la sección de configuración.</summary>\n    public const string SectionName = \"Leaderboard\";\n\n    /// <summary>Cantidad de posiciones que devuelve GET /api/scores si no se indica top.</summary>\n    public int DefaultTop { get; set; } = 10;\n\n    /// <summary>Máximo valor permitido para top.</summary>\n    public int MaxTop { get; set; } = 50;\n\n    /// <summary>Puntaje máximo aceptado.</summary>\n    public int MaxScore { get; set; } = 1_000_000;\n\n    /// <summary>Largo máximo de playerId.</summary>\n    public int MaxPlayerIdLength { get; set; } = 32;\n}\n", "Program.cs": "using Leaderboard.Api;\n\nvar app = AppBuilder.Build(args);\napp.Run();\n", "appsettings.json": "{\n  \"Logging\": { \"LogLevel\": { \"Default\": \"Warning\" } },\n  \"Leaderboard\": {\n    \"DefaultTop\": 10,\n    \"MaxTop\": 50,\n    \"MaxScore\": 1000000,\n    \"MaxPlayerIdLength\": 32\n  }\n}\n", "docs/CONVENTIONS.md": "# Convenciones .NET (Leaderboard.Api)\n\n- .NET 8+, `Nullable` habilitado, file-scoped namespaces `Leaderboard.Api.<Carpeta>`.\n- DTOs de entrada/salida como `record` (en `Contracts/` o junto al endpoint).\n- Todo acceso a datos es asíncrono y recibe el `CancellationToken` del request. Prohibido `.Result`,\n  `.Wait()` y `GetAwaiter().GetResult()`.\n- Dependencias por inyección (DI): nada de `new InMemoryScoreRepository()` ni estado `static` mutable\n  en los endpoints.\n- Los límites vienen de `LeaderboardOptions` (`IOptions<LeaderboardOptions>`), nunca números sueltos.\n  `Legacy/OldLimits` está obsoleto.\n- Errores de validación: `Results.ValidationProblem(...)` (400 con ProblemDetails y el diccionario\n  `errors` indexado por el nombre del campo, en camelCase). No encontrado: `Results.NotFound()`.\n- Logs con `ILogger<T>`; prohibido `Console.WriteLine`.\n- Comentarios `/// <summary>` en tipos y miembros públicos.\n- `dotnet build` sin warnings.\n", "docs/tasks/NET-501.md": "# NET-501: API del leaderboard\n\nArchivos permitidos: `Endpoints/ScoreEndpoints.cs` e `Infrastructure/InMemoryScoreRepository.cs`.\nLos DTOs ya existen en `Contracts/ScoreContracts.cs` (úsalos; no los modifiques). No modifiques nada más.\n\nEndpoints (JSON en camelCase):\n\n1. `POST /api/scores` con cuerpo `SubmitScoreRequest` (`{ \"playerId\": \"ana_01\", \"score\": 1200 }`).\n   - `playerId`: obligatorio, 1..`MaxPlayerIdLength` caracteres, solo letras, números, `_` o `-`.\n   - `score`: entero entre 0 y `MaxScore`.\n   - Inválido → 400 `ValidationProblem` con la clave del campo (`playerId` o `score`).\n   - Válido → 201 Created, cabecera `Location: /api/scores/{playerId}` y cuerpo `ScoreResponse` con el\n     **mejor** puntaje del jugador (un puntaje menor no reemplaza al mejor) y su posición actual.\n2. `GET /api/scores?top=N` → 200 con una lista de `ScoreResponse` ordenada por puntaje descendente; en\n   empate va primero quien lo logró antes. `rank` empieza en 1. `top` es opcional: por defecto\n   `DefaultTop`; si piden más de `MaxTop`, se devuelven como máximo `MaxTop`.\n\nEl repositorio en memoria tiene bugs: reemplaza el mejor puntaje por uno menor y se corrompe con\npeticiones simultáneas (el leaderboard recibe muchos envíos en paralelo). Corrígelo.\n\nCumple `docs/CONVENTIONS.md`.\n"}, "firebase": {"data/rtdb_export.json": "{\n  \"users\": {\n    \"uA1\": {\n      \"displayName\": \"  Ana María  \",\n      \"score\": \"1200\",\n      \"lastLogin\": 1728000000000,\n      \"inventory\": { \"0\": \"sword\", \"1\": \"potion\", \"2\": \"potion\" },\n      \"settings\": { \"music\": \"true\", \"sfx\": \"false\" }\n    },\n    \"uB2\": {\n      \"score\": 860,\n      \"lastLogin\": 1727000000000,\n      \"inventory\": [null, \"shield\", null, \"bow\"],\n      \"settings\": { \"music\": false }\n    },\n    \"uC3\": {\n      \"displayName\": \"Tramposo\",\n      \"score\": \"9999999\",\n      \"banned\": true\n    },\n    \"uD4\": {\n      \"displayName\": \"Un nombre larguísimo para un jugador\",\n      \"score\": \"mil\",\n      \"lastLogin\": \"ayer\"\n    }\n  },\n  \"config\": { \"maintenance\": false }\n}\n", "docs/CONVENTIONS.md": "# Convenciones (datos y Firebase)\n\n- TypeScript estricto: nada de `any` (usa `unknown` + validaciones de tipo), sin `@ts-ignore`,\n  sin `var`, sin `export default`, sin `console.log`.\n- Las funciones no mutan sus parámetros: construyen objetos nuevos.\n- Los valores del esquema vienen de `src/config/schema.ts` (no copies números ni textos).\n  `src/legacy/` está obsoleto.\n- JSDoc `/** */` en cada función exportada.\n- Los archivos `.json` deben ser JSON válido (sin comentarios ni comas finales).\n- Reglas de Firestore: `rules_version = '2'`, deniega por defecto y da a cada usuario acceso solo a lo suyo.\n", "docs/tasks/FB-601.md": "# FB-601: Migración de Realtime Database a Firestore\n\nArchivos permitidos: `src/migrate.ts`, `firestore.rules`, `firestore.indexes.json`.\n(`data/rtdb_export.json` es un ejemplo real del export; no lo modifiques.)\n\n## 1. `migrateUsers(rtdb: unknown): MigrationResult` en `src/migrate.ts`\n\nEntrada: el JSON exportado de Realtime Database (ver el ejemplo). Por cada usuario de `users`:\n\n- `displayName`: sin espacios al inicio/fin; si falta o queda vacío usa el nombre por defecto del\n  esquema; si es más largo que el máximo del esquema se recorta a ese largo.\n- `score`: puede venir como número o como texto numérico. Debe quedar como entero entre 0 y el\n  máximo del esquema. Si no es válido → `score: 0` y se agrega un error `{ uid, field: \"score\", message }`.\n- `lastLogin`: milisegundos desde epoch → texto ISO (`new Date(ms).toISOString()`). Si falta → `null`.\n  Si no es un número válido → `null` y error con `field: \"lastLogin\"`.\n- `inventory`: Realtime Database guarda las listas como arreglo **con huecos (`null`)** o como objeto con\n  claves numéricas `{\"0\": ..., \"1\": ...}`. Debe quedar un `string[]` sin huecos, en orden por índice.\n  Si falta → `[]`.\n- `settings`: valores booleanos que pueden venir como `true/false` o como texto `\"true\"/\"false\"`.\n  Deben quedar como booleanos; los que no se puedan interpretar se omiten. Si falta → `{}`.\n- Los usuarios con `banned: true` **no** se migran (no es un error).\n- La función no modifica la entrada. Si la entrada no es un objeto o no tiene `users` como objeto,\n  devuelve `{ users: {}, errors: [{ uid: \"*\", field: \"users\", message }] }` (sin lanzar excepciones).\n\n## 2. `firestore.rules`\n\n- `users/{uid}`: lectura para cualquier usuario autenticado. Crear/actualizar solo el propio\n  documento (`request.auth.uid == uid`) y solo si `score` es entero (`is int`) y `displayName` es\n  texto de como máximo 24 caracteres. Borrar: nunca.\n- Todo lo demás denegado (elimina la regla abierta actual).\n\n## 3. `firestore.indexes.json`\n\nÍndice compuesto para la consulta del ranking: colección `users`, `score` descendente y luego\n`lastLogin` descendente (`queryScope: \"COLLECTION\"`), con el formato estándar de Firebase CLI.\n\nCumple `docs/CONVENTIONS.md`.\n", "firebase.json": "{\n  \"firestore\": {\n    \"rules\": \"firestore.rules\",\n    \"indexes\": \"firestore.indexes.json\"\n  }\n}\n", "firestore.indexes.json": "{\n  \"indexes\": [],\n  \"fieldOverrides\": []\n}\n", "firestore.rules": "rules_version = '2';\nservice cloud.firestore {\n  match /databases/{database}/documents {\n    // TODO FB-601: reglas de producción\n    match /{document=**} {\n      allow read, write: if true;\n    }\n  }\n}\n", "src/config/schema.ts": "/** Reglas de datos vigentes del juego. */\nexport const USER_SCHEMA = {\n  /** Nombre que se asigna si el usuario no tiene uno. */\n  defaultDisplayName: \"Jugador\",\n  /** Largo máximo del nombre visible. */\n  maxDisplayNameLength: 24,\n  /** Puntaje máximo creíble (por encima se considera inválido). */\n  maxScore: 1_000_000,\n} as const;\n", "src/legacy/oldSchema.ts": "/** @deprecated Esquema de la v1 (Realtime Database). No usar. */\nexport const OLD_SCHEMA = { maxName: 16, defaultName: \"Player\" };\n", "src/migrate.ts": "import type { MigrationResult } from \"./types\";\n\n/**\n * Convierte el export de Realtime Database en documentos de Firestore.\n * Ver docs/tasks/FB-601.md.\n */\nexport function migrateUsers(rtdb: unknown): MigrationResult {\n  return { users: {}, errors: [] };\n}\n", "src/types.ts": "/** Documento de usuario en Firestore (colección `users`, id = uid). */\nexport interface FirestoreUser {\n  displayName: string;\n  /** Puntaje entero >= 0. */\n  score: number;\n  /** Fecha ISO 8601 (UTC) o null si no se conoce. */\n  lastLogin: string | null;\n  /** Objetos del inventario, sin huecos, en el orden original. */\n  inventory: string[];\n  /** Preferencias booleanas. */\n  settings: Record<string, boolean>;\n}\n\n/** Problema encontrado al migrar un usuario. */\nexport interface MigrationError {\n  uid: string;\n  field: string;\n  message: string;\n}\n\n/** Resultado de la migración. */\nexport interface MigrationResult {\n  users: Record<string, FirestoreUser>;\n  errors: MigrationError[];\n}\n"}}
EXTRA_TESTS = {"CPP-301": "// Tests de comportamiento CPP-301. Imprime @@RESULT@@{json}\n#include <cstdio>\n#include <algorithm>\n#include <functional>\n#include <map>\n#include <string>\n#include <type_traits>\n#include <vector>\n#include \"event_queue.hpp\"\n\nstatic std::vector<std::pair<std::string, bool>> g_results;\nstatic void check(const char* name, const std::function<bool()>& f) {\n    bool ok = false;\n    try { ok = f(); } catch (...) { ok = false; }\n    g_results.emplace_back(name, ok);\n}\nstatic std::string esc(const std::string& s) { std::string o; for (char c : s) { if (c == '\"' || c == '\\\\') o += '\\\\'; o += c; } return o; }\n\nusing bench::Event;\nusing bench::EventQueue;\n\nint main() {\n    check(\"pop en cola vacía devuelve optional vacío\", [] {\n        EventQueue q;\n        auto r = q.pop();\n        return !r.has_value();\n    });\n    check(\"size() es const y devuelve size_t\", [] {\n        const EventQueue q;\n        return std::is_same<decltype(q.size()), std::size_t>::value && q.size() == 0;\n    });\n    check(\"mayor prioridad sale primero\", [] {\n        EventQueue q;\n        q.push({\"a\", 1, 0}); q.push({\"b\", 7, 0}); q.push({\"c\", 4, 0});\n        auto x = q.pop(); auto y = q.pop(); auto z = q.pop();\n        return x && y && z && x->name == \"b\" && y->name == \"c\" && z->name == \"a\" && q.size() == 0;\n    });\n    check(\"empates salen en orden de llegada (FIFO)\", [] {\n        EventQueue q;\n        for (int i = 0; i < 6; ++i) q.push({\"e\" + std::to_string(i), 5, 0});\n        for (int i = 0; i < 6; ++i) { auto e = q.pop(); if (!e || e->name != \"e\" + std::to_string(i)) return false; }\n        return true;\n    });\n    check(\"prioridades fuera de rango se rechazan\", [] {\n        EventQueue q;\n        return !q.push({\"neg\", -1, 0}) && !q.push({\"big\", 11, 0}) && q.push({\"ok0\", 0, 0}) && q.push({\"ok10\", 10, 0}) && q.size() == 2;\n    });\n    check(\"cola llena: evento más prioritario expulsa al menos prioritario más reciente\", [] {\n        EventQueue q;\n        for (int i = 0; i < 8; ++i) q.push({\"p\" + std::to_string(i), i < 2 ? 1 : 5, 0});  // p0,p1 prio 1\n        bool in = q.push({\"urgent\", 9, 0});\n        if (!in || q.size() != 8) return false;\n        std::vector<std::string> names;\n        while (auto e = q.pop()) names.push_back(e->name);\n        // p1 (prio 1, el más reciente de los menos prioritarios) debe haber salido; p0 se queda al final\n        return names.front() == \"urgent\" && names.back() == \"p0\" &&\n               std::find(names.begin(), names.end(), \"p1\") == names.end();\n    });\n    check(\"cola llena: evento no más prioritario se rechaza\", [] {\n        EventQueue q;\n        for (int i = 0; i < 8; ++i) q.push({\"p\" + std::to_string(i), 3, 0});\n        return !q.push({\"same\", 3, 0}) && !q.push({\"low\", 1, 0}) && q.size() == 8;\n    });\n    check(\"drainUntil saca todos los vencidos aunque haya otros más prioritarios pendientes\", [] {\n        EventQueue q;\n        q.push({\"future_hi\", 9, 5.0}); q.push({\"now_lo\", 1, 1.0}); q.push({\"now_mid\", 4, 0.5}); q.push({\"now_mid2\", 4, 2.0});\n        auto out = q.drainUntil(2.0);\n        return out.size() == 3 && out[0].name == \"now_mid\" && out[1].name == \"now_mid2\" && out[2].name == \"now_lo\" &&\n               q.size() == 1 && q.pop()->name == \"future_hi\";\n    });\n    check(\"muchas operaciones sin perder ni duplicar eventos\", [] {\n        EventQueue q; int pushed = 0, popped = 0;\n        for (int round = 0; round < 200; ++round) {\n            if (q.push({\"r\", round % 11, round * 0.1})) ++pushed;\n            if (round % 3 == 0 && q.pop()) ++popped;\n        }\n        while (q.pop()) ++popped;\n        return popped <= pushed && q.size() == 0 && popped > 0;\n    });\n    check(\"se puede copiar/mover la cola de forma segura\", [] {\n        EventQueue a; a.push({\"x\", 2, 0}); a.push({\"y\", 8, 0});\n        EventQueue b = a; EventQueue c = std::move(a);\n        auto pb = b.pop(); auto pc = c.pop();\n        return pb && pc && pb->name == \"y\" && pc->name == \"y\" && b.size() == 1;\n    });\n    std::string js = \"{\\\"checks\\\":{\";\n    for (size_t i = 0; i < g_results.size(); ++i) { if (i) js += \",\"; js += \"\\\"\" + esc(g_results[i].first) + \"\\\":\" + (g_results[i].second ? \"true\" : \"false\"); }\n    js += \"},\\\"notes\\\":[]}\";\n    std::printf(\"@@RESULT@@%s\\n\", js.c_str());\n    return 0;\n}\n", "UE-302": "// Tests de comportamiento UE-302 (contra los stubs de Unreal). Imprime @@RESULT@@{json}\n#define _ALLOW_KEYWORD_MACROS\n#include <algorithm>\n#include <array>\n#include <cmath>\n#include <cstdint>\n#include <cstdio>\n#include <cstring>\n#include <functional>\n#include <limits>\n#include <map>\n#include <memory>\n#include <optional>\n#include <string>\n#include <unordered_map>\n#include <utility>\n#include <vector>\n// Los tests leen MaxHealth/CurrentHealth directamente: la tarea no exige que sean públicos\n// (protected/private con UPROPERTY es válido en Unreal), así que se abren solo para el test.\n#define protected public\n#define private public\n#include \"Characters/ArenaCharacter.h\"\n#include \"Components/HealthComponent.h\"\n#include \"Pickups/HealthPickup.h\"\n\nstatic std::vector<std::pair<std::string, bool>> g_results;\nstatic void run_check(const char* name, const std::function<bool()>& f) {\n    bool ok = false;\n    try { ok = f(); } catch (...) { ok = false; }\n    g_results.emplace_back(name, ok);\n}\nstatic bool near(float a, float b) { return std::fabs(a - b) < 0.01f; }\n\nclass FListener : public UObject {\npublic:\n    int32 Changes = 0, Deaths = 0;\n    float LastHealth = -1.f, LastDelta = 0.f;\n    void OnChanged(float NewHealth, float Delta) { ++Changes; LastHealth = NewHealth; LastDelta = Delta; }\n    void OnDied() { ++Deaths; }\n};\n\nstatic UHealthComponent* MakeComp(FListener* L) {\n    auto* C = NewObject<UHealthComponent>();\n    C->OnHealthChanged.AddDynamic(L, &FListener::OnChanged);\n    C->OnDeath.AddDynamic(L, &FListener::OnDied);\n    static_cast<UActorComponent*>(C)->BeginPlay();\n    return C;\n}\n\nint main() {\n    run_check(\"vida inicial = valor de balance (150)\", [] { FListener L; auto* C = MakeComp(&L); return near(C->MaxHealth, 150.f) && near(C->CurrentHealth, 150.f) && !C->IsDead(); });\n    run_check(\"daño baja la vida y emite delta negativo\", [] { FListener L; auto* C = MakeComp(&L);\n        bool r = C->ApplyDamage(30.f); return r && near(C->CurrentHealth, 120.f) && L.Changes == 1 && near(L.LastHealth, 120.f) && near(L.LastDelta, -30.f); });\n    run_check(\"daño <= 0 se ignora\", [] { FListener L; auto* C = MakeComp(&L); return !C->ApplyDamage(0.f) && !C->ApplyDamage(-5.f) && L.Changes == 0 && near(C->CurrentHealth, 150.f); });\n    run_check(\"muerte: vida 0, OnDeath una sola vez, daño posterior ignorado\", [] { FListener L; auto* C = MakeComp(&L);\n        C->ApplyDamage(500.f); bool again = C->ApplyDamage(10.f);\n        return near(C->CurrentHealth, 0.f) && C->IsDead() && L.Deaths == 1 && !again && near(L.LastDelta, -150.f); });\n    run_check(\"curación no pasa del máximo y emite delta positivo\", [] { FListener L; auto* C = MakeComp(&L);\n        C->ApplyDamage(20.f); bool r = C->Heal(50.f); return r && near(C->CurrentHealth, 150.f) && near(L.LastDelta, 20.f); });\n    run_check(\"curar con vida llena, <= 0 o muerto no hace nada\", [] { FListener L; auto* C = MakeComp(&L);\n        bool full = C->Heal(10.f); bool neg = C->Heal(-3.f); C->ApplyDamage(999.f); int32 before = L.Changes; bool dead = C->Heal(50.f);\n        return !full && !neg && !dead && L.Changes == before && near(C->CurrentHealth, 0.f); });\n    run_check(\"integración: personaje y botiquín\", [] { auto* Ch = NewObject<AArenaCharacter>(); Ch->BeginPlay();\n        Ch->HealthComponent->ApplyDamage(60.f); auto* P = NewObject<AHealthPickup>(); P->Consume(Ch);\n        bool healed = near(Ch->HealthComponent->CurrentHealth, 130.f) && P->IsPendingKill();\n        Ch->HealthComponent->ApplyDamage(1000.f); return healed && Ch->bIsDowned && Ch->HudUpdates == 3; });\n    std::string js = \"{\\\"checks\\\":{\";\n    for (size_t i = 0; i < g_results.size(); ++i) { if (i) js += \",\"; js += \"\\\"\" + g_results[i].first + \"\\\":\" + (g_results[i].second ? \"true\" : \"false\"); }\n    js += \"},\\\"notes\\\":[]}\";\n    std::printf(\"@@RESULT@@%s\\n\", js.c_str());\n    return 0;\n}\n", "RS-401": "// Tests ocultos RS-401 (los agrega el calificador como tests/hidden.rs)\nuse savegame::{parse_save, to_save_string, SaveData, SaveError};\nuse std::collections::BTreeMap;\n\nconst OK: &str = \"# partida\\nversion=2\\nplayer=Rodrigo\\ngold=1500\\n\\nitem=potion:3\\nitem=sword:1\\n\";\n\n#[test]\nfn lee_partida_valida() {\n    let d = parse_save(OK).unwrap();\n    assert_eq!(d.version, 2);\n    assert_eq!(d.player, \"Rodrigo\");\n    assert_eq!(d.gold, 1500);\n    assert_eq!(d.items.get(\"potion\"), Some(&3));\n    assert_eq!(d.items.get(\"sword\"), Some(&1));\n}\n\n#[test]\nfn ignora_espacios_comentarios_y_vacias() {\n    let d = parse_save(\"\\n  # hola\\n version = 2 \\n player =  Ana \\n\\n\").unwrap();\n    assert_eq!(d.player, \"Ana\");\n    assert_eq!(d.gold, 0);\n    assert!(d.items.is_empty());\n}\n\n#[test]\nfn linea_sin_igual_es_malformed_con_numero_real() {\n    assert_eq!(parse_save(\"# c\\nversion=2\\nplayer=A\\nbasura\\n\"), Err(SaveError::Malformed { line: 4 }));\n}\n\n#[test]\nfn clave_desconocida() {\n    assert_eq!(parse_save(\"version=2\\nplayer=A\\nhp=10\\n\"), Err(SaveError::UnknownKey { line: 3, key: \"hp\".into() }));\n}\n\n#[test]\nfn faltan_campos_obligatorios() {\n    assert_eq!(parse_save(\"player=A\\n\"), Err(SaveError::MissingField(\"version\")));\n    assert_eq!(parse_save(\"version=2\\n\"), Err(SaveError::MissingField(\"player\")));\n    assert_eq!(parse_save(\"version=2\\nplayer=  \\n\"), Err(SaveError::MissingField(\"player\")));\n}\n\n#[test]\nfn version_no_soportada() {\n    assert_eq!(parse_save(\"version=1\\nplayer=A\\n\"), Err(SaveError::UnsupportedVersion(1)));\n    assert!(matches!(parse_save(\"version=dos\\nplayer=A\\n\"), Err(SaveError::InvalidNumber { line: 1, .. })));\n}\n\n#[test]\nfn oro_invalido() {\n    assert!(matches!(parse_save(\"version=2\\nplayer=A\\ngold=-5\\n\"), Err(SaveError::InvalidNumber { line: 3, .. })));\n    assert!(matches!(parse_save(\"version=2\\nplayer=A\\ngold=99999999999\\n\"), Err(SaveError::InvalidNumber { line: 3, .. })));\n    assert!(matches!(parse_save(\"version=2\\nplayer=A\\ngold=1.5\\n\"), Err(SaveError::InvalidNumber { .. })));\n}\n\n#[test]\nfn objetos_repetidos_se_suman_y_respetan_pila() {\n    let d = parse_save(\"version=2\\nplayer=A\\nitem=arrow:60\\nitem=arrow:39\\n\").unwrap();\n    assert_eq!(d.items.get(\"arrow\"), Some(&99));\n    assert_eq!(\n        parse_save(\"version=2\\nplayer=A\\nitem=arrow:60\\nitem=arrow:40\\n\"),\n        Err(SaveError::StackOverflow { item: \"arrow\".into() })\n    );\n}\n\n#[test]\nfn cantidad_invalida_o_item_malformado() {\n    assert!(matches!(parse_save(\"version=2\\nplayer=A\\nitem=arrow:0\\n\"), Err(SaveError::InvalidNumber { line: 3, .. })));\n    assert!(matches!(parse_save(\"version=2\\nplayer=A\\nitem=arrow:x\\n\"), Err(SaveError::InvalidNumber { line: 3, .. })));\n}\n\n#[test]\nfn ida_y_vuelta() {\n    let mut items = BTreeMap::new();\n    items.insert(\"zeta\".to_string(), 2);\n    items.insert(\"alfa\".to_string(), 99);\n    let d = SaveData { version: 2, player: \"Lu\".into(), gold: 7, items };\n    let text = to_save_string(&d);\n    assert_eq!(text, \"version=2\\nplayer=Lu\\ngold=7\\nitem=alfa:99\\nitem=zeta:2\\n\");\n    assert_eq!(parse_save(&text), Ok(d));\n}\n\n#[test]\nfn no_entra_en_panico_con_basura() {\n    for junk in [\"\", \"=\", \"==\", \"version=\", \"item=::\", \"version=2\\nplayer=A\\nitem=a:b:c\\n\", \"\\u{0}\\u{1}=x\"] {\n        let r = std::panic::catch_unwind(|| parse_save(junk));\n        assert!(r.is_ok(), \"panic con {:?}\", junk);\n    }\n}\n", "NET-501": "// Tests de integración NET-501: levanta la API en un puerto libre y la prueba por HTTP. Imprime @@RESULT@@{json}\nusing System.Net;\nusing System.Net.Http.Json;\nusing System.Text.Json;\nusing Microsoft.AspNetCore.Hosting.Server;\nusing Microsoft.AspNetCore.Hosting.Server.Features;\n\npublic static class BenchHarness\n{\n    private static readonly Dictionary<string, bool> Results = new();\n    private static readonly List<string> Notes = new();\n\n    private static async Task Check(string name, Func<Task<bool>> f)\n    {\n        try { Results[name] = await f().WaitAsync(TimeSpan.FromSeconds(20)); }\n        catch (Exception e) { Results[name] = false; Notes.Add($\"{name}: {e.GetType().Name}: {e.Message}\"); }\n    }\n\n    public static async Task<int> Main()\n    {\n        var app = Leaderboard.Api.AppBuilder.Build(new[] { \"--urls\", \"http://127.0.0.1:0\", \"--Logging:LogLevel:Default=None\" });\n        await app.StartAsync();\n        var addr = app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First();\n        using var http = new HttpClient { BaseAddress = new Uri(addr) };\n        async Task<HttpResponseMessage> Post(object body) => await http.PostAsJsonAsync(\"/api/scores\", body);\n        async Task<JsonElement> Json(HttpResponseMessage r) => JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement;\n        async Task<bool> IsValidation(HttpResponseMessage r, string key)\n        {\n            if (r.StatusCode != HttpStatusCode.BadRequest) return false;\n            var j = await Json(r);\n            return j.TryGetProperty(\"errors\", out var errs) && errs.EnumerateObject().Any(p => string.Equals(p.Name, key, StringComparison.Ordinal));\n        }\n\n        await Check(\"POST válido → 201 con Location y rank\", async () =>\n        {\n            var r = await Post(new { playerId = \"ana_01\", score = 1200 });\n            if (r.StatusCode != HttpStatusCode.Created) return false;\n            var j = await Json(r);\n            return r.Headers.Location?.ToString() == \"/api/scores/ana_01\" && j.GetProperty(\"playerId\").GetString() == \"ana_01\" &&\n                   j.GetProperty(\"score\").GetInt32() == 1200 && j.GetProperty(\"rank\").GetInt32() == 1;\n        });\n        await Check(\"un puntaje menor no reemplaza al mejor\", async () =>\n        {\n            var r = await Post(new { playerId = \"ana_01\", score = 50 });\n            var j = await Json(r);\n            return (int)r.StatusCode == 201 && j.GetProperty(\"score\").GetInt32() == 1200;\n        });\n        await Check(\"playerId inválido → 400 ValidationProblem (playerId)\", async () =>\n            await IsValidation(await Post(new { playerId = \"\", score = 10 }), \"playerId\") &&\n            await IsValidation(await Post(new { playerId = \"con espacio\", score = 10 }), \"playerId\") &&\n            await IsValidation(await Post(new { playerId = new string('x', 33), score = 10 }), \"playerId\") &&\n            await IsValidation(await Post(new { score = 10 }), \"playerId\"));\n        await Check(\"score fuera de rango → 400 ValidationProblem (score)\", async () =>\n            await IsValidation(await Post(new { playerId = \"bob\", score = -1 }), \"score\") &&\n            await IsValidation(await Post(new { playerId = \"bob\", score = 1000001 }), \"score\"));\n        await Check(\"límites exactos aceptados (score 0 y 1000000, id de 32)\", async () =>\n            (int)(await Post(new { playerId = \"zero\", score = 0 })).StatusCode == 201 &&\n            (int)(await Post(new { playerId = \"max\", score = 1000000 })).StatusCode == 201 &&\n            (int)(await Post(new { playerId = new string('y', 32), score = 5 })).StatusCode == 201);\n        await Check(\"GET top ordenado, empates por antigüedad y rank desde 1\", async () =>\n        {\n            await Post(new { playerId = \"tie_a\", score = 700 });\n            await Post(new { playerId = \"tie_b\", score = 700 });\n            var list = await http.GetFromJsonAsync<JsonElement>(\"/api/scores?top=5\");\n            var ids = list.EnumerateArray().Select(e => e.GetProperty(\"playerId\").GetString()).ToList();\n            var ranks = list.EnumerateArray().Select(e => e.GetProperty(\"rank\").GetInt32()).ToList();\n            return ids.SequenceEqual(new[] { \"max\", \"ana_01\", \"tie_a\", \"tie_b\", new string('y', 32) }) && ranks.SequenceEqual(new[] { 1, 2, 3, 4, 5 });\n        });\n        await Check(\"top por defecto es DefaultTop (10)\", async () =>\n        {\n            for (var i = 0; i < 12; i++) await Post(new { playerId = $\"bulk{i}\", score = 10 + i });\n            var list = await http.GetFromJsonAsync<JsonElement>(\"/api/scores\");\n            return list.GetArrayLength() == 10;\n        });\n        await Check(\"200 envíos en paralelo sin perder datos\", async () =>\n        {\n            var tasks = Enumerable.Range(0, 200).Select(i => Post(new { playerId = $\"par{i % 40}\", score = i })).ToArray();\n            var res = await Task.WhenAll(tasks);\n            if (res.Any(r => (int)r.StatusCode != 201)) return false;\n            var all = await http.GetFromJsonAsync<JsonElement>(\"/api/scores?top=50\");\n            var best = all.EnumerateArray().Where(e => e.GetProperty(\"playerId\").GetString()!.StartsWith(\"par\"))\n                .ToDictionary(e => e.GetProperty(\"playerId\").GetString()!, e => e.GetProperty(\"score\").GetInt32());\n            return best.Count == 40 && Enumerable.Range(0, 40).All(p => best.TryGetValue($\"par{p}\", out var s) && s == 160 + p);\n        });\n        await Check(\"top mayor que MaxTop → como máximo 50\", async () =>\n        {\n            for (var i = 0; i < 30; i++) await Post(new { playerId = $\"extra{i}\", score = 5 });\n            var list = await http.GetFromJsonAsync<JsonElement>(\"/api/scores?top=500\");\n            return list.GetArrayLength() == 50;\n        });\n        await app.StopAsync();\n        Console.WriteLine(\"@@RESULT@@\" + JsonSerializer.Serialize(new { checks = Results, notes = Notes }));\n        return 0;\n    }\n}\n", "FB-601": "// Tests de comportamiento FB-601 (migrateUsers). Uso: node fb601_tests.js <workDir>\n\"use strict\";\nconst path = require(\"path\");\nconst fs = require(\"fs\");\nconst work = path.resolve(process.argv[2]);\nconst results = {}; const notes = [];\nfunction check(name, fn) { try { results[name] = !!fn(); } catch (e) { results[name] = false; notes.push(name + \": \" + (e && e.message)); } }\nlet migrateUsers;\ntry { ({ migrateUsers } = require(path.join(work, \"out\", \"migrate.js\"))); } catch (e) { notes.push(\"no carga migrate.js: \" + e.message); }\nconst sample = () => JSON.parse(fs.readFileSync(path.join(work, \"data\", \"rtdb_export.json\"), \"utf8\"));\nconst run = (x) => migrateUsers(x);\ncheck(\"migra los usuarios no baneados (y omite baneados sin error)\", () => {\n  const r = run(sample()); return Object.keys(r.users).sort().join(\",\") === \"uA1,uB2,uD4\" && !r.errors.some((e) => e.uid === \"uC3\");\n});\ncheck(\"displayName: trim, por defecto y recorte a 24\", () => {\n  const u = run(sample()).users; return u.uA1.displayName === \"Ana María\" && u.uB2.displayName === \"Jugador\" && u.uD4.displayName === \"Un nombre larguísimo par\" && u.uD4.displayName.length === 24;\n});\ncheck(\"score: texto numérico a entero, inválido → 0 con error\", () => {\n  const r = run(sample()); return r.users.uA1.score === 1200 && r.users.uB2.score === 860 && r.users.uD4.score === 0 &&\n    r.errors.some((e) => e.uid === \"uD4\" && e.field === \"score\");\n});\ncheck(\"score fuera de rango o decimal → error\", () => {\n  const r = run({ users: { a: { score: 1000001 }, b: { score: \"12.5\" }, c: { score: -3 }, d: { score: 1000000 } } });\n  return r.users.a.score === 0 && r.users.b.score === 0 && r.users.c.score === 0 && r.users.d.score === 1000000 &&\n    [\"a\", \"b\", \"c\"].every((id) => r.errors.some((e) => e.uid === id && e.field === \"score\"));\n});\ncheck(\"lastLogin: ms → ISO, falta → null, inválido → null con error\", () => {\n  const r = run(sample()); return r.users.uA1.lastLogin === new Date(1728000000000).toISOString() &&\n    r.users.uD4.lastLogin === null && r.errors.some((e) => e.uid === \"uD4\" && e.field === \"lastLogin\") &&\n    run({ users: { x: { score: 1 } } }).users.x.lastLogin === null;\n});\ncheck(\"inventory: objeto indexado y arreglo con huecos → lista compacta en orden\", () => {\n  const u = run(sample()).users; const o = run({ users: { z: { score: 1, inventory: { \"10\": \"c\", \"2\": \"b\", \"0\": \"a\" } } } }).users.z;\n  return JSON.stringify(u.uA1.inventory) === '[\"sword\",\"potion\",\"potion\"]' && JSON.stringify(u.uB2.inventory) === '[\"shield\",\"bow\"]' &&\n    JSON.stringify(u.uD4.inventory) === \"[]\" && JSON.stringify(o.inventory) === '[\"a\",\"b\",\"c\"]';\n});\ncheck(\"settings: texto 'true'/'false' → booleanos, falta → {}\", () => {\n  const u = run(sample()).users; const s = run({ users: { y: { score: 1, settings: { a: \"true\", b: false, c: \"quizás\", d: 1 } } } }).users.y.settings;\n  return u.uA1.settings.music === true && u.uA1.settings.sfx === false && u.uB2.settings.music === false &&\n    JSON.stringify(u.uD4.settings) === \"{}\" && JSON.stringify(s) === '{\"a\":true,\"b\":false}';\n});\ncheck(\"no modifica la entrada\", () => { const input = sample(); const before = JSON.stringify(input); run(input); return JSON.stringify(input) === before; });\ncheck(\"entrada inválida → error users sin lanzar\", () => [null, 42, \"x\", [], {}, { users: [] }, { users: null }].every((bad) => {\n  const r = run(bad); return Object.keys(r.users).length === 0 && r.errors.length === 1 && r.errors[0].uid === \"*\" && r.errors[0].field === \"users\";\n}));\nprocess.stdout.write(\"@@RESULT@@\" + JSON.stringify({ checks: results, notes }) + \"\\n\");\n"}
PROJECTS.update(EXTRA_PROJECTS)
BENCH_VERSION = "v4"
# Tarea más representativa de cada categoría para --rapido.
QUICK_TASKS = {"unity": "T-103", "web": "W-202", "cpp": "CPP-301", "unreal": "UE-302", "rust": "RS-401",
               "dotnet": "NET-501", "firebase": "FB-601", "mcp": "MCP-701"}
TASK_WALL_SECONDS = 300   # límite duro por tarea (5 min); el objetivo es terminar en ≤ 3 min
MAX_STEPS = 25
TARGET_SECONDS = 180
PROJECTS["web"]["docs/tasks/W-202.md"] = "# W-202: Buscador con autocompletado\n\nCrear: `src/ui/searchBox.ts` (no modificar ningún otro archivo).\n\nExporta exactamente esta función:\n\n```ts\nexport function initSearchBox(\n  root: HTMLElement,\n  search: (query: string) => Promise<Product[]>,\n  options?: { debounceMs?: number }\n): void;\n```\n\n`root` ya contiene este HTML:\n\n```html\n<div class=\"search-box\">\n  <input class=\"search-box__input\" type=\"search\">\n  <ul class=\"search-box__results\" id=\"search-results\"></ul>\n  <p class=\"search-box__status\"></p>\n</div>\n```\n\nComportamiento:\n- Escucha el evento `input` del campo. Espera `debounceMs` (por defecto 300) sin nuevas teclas antes\n  de llamar a `search` con el texto sin espacios al inicio/final.\n- Si el texto tiene menos de 2 caracteres: no llama a `search`, vacía la lista y el estado.\n- Por cada producto agrega `<li class=\"search-box__item\">Nombre — $12.34</li>` (precio con 2 decimales a\n  partir de `priceCents`). El nombre viene del servidor y **puede contener HTML**: debe mostrarse como\n  texto literal.\n- Sin resultados: lista vacía y el estado (`.search-box__status`) dice `Sin resultados`.\n- Si `search` falla: lista vacía y el estado dice `Error al buscar`.\n- Accesibilidad: el input debe quedar con `aria-controls=\"search-results\"` y el estado con\n  `aria-live=\"polite\"`.\n- Cumple `docs/CONVENTIONS.md`.\n"
PROJECTS["web"]["docs/tasks/W-203.md"] = "# W-203: Paginación y validación en GET /api/products\n\nArchivo: `src/api/products.ts` (no modificar ningún otro archivo).\n\nParámetros de query (opcionales, llegan como string):\n- `page`: entero >= 1. Por defecto 1.\n- `pageSize`: entero entre 1 y el máximo vigente de la API. Por defecto, el tamaño vigente por defecto.\n  Los límites vigentes están definidos en `src/config` (búscalos; no los copies como números).\n\nRespuesta 200:\n```json\n{ \"items\": [...], \"page\": 1, \"pageSize\": 12, \"total\": 30, \"totalPages\": 3 }\n```\n`totalPages` es 0 si no hay productos. Pedir una página mayor a `totalPages` devuelve 200 con\n`items: []`.\n\nRespuesta 400 si algún parámetro es inválido (no numérico, decimal o fuera de rango):\n```json\n{ \"error\": { \"code\": \"INVALID_QUERY\", \"field\": \"pageSize\" } }\n```\n\nMantén la firma de `handleGetProducts` y cumple `docs/CONVENTIONS.md`.\n"
# Casos extra de endurecimiento (v4), surgidos de defectos que la revisión de Claude encontró y los tests no cubrían.
EXTRA_TESTS["RS-401"] = EXTRA_TESTS["RS-401"].rstrip("\n") + "\n" + (Path(__file__).resolve().parent / "tests" / "rs401_extra.rs").read_text(encoding="utf-8")
_fb_tail = 'process.stdout.write("@@RESULT@@"'
_fb_extra = (Path(__file__).resolve().parent / "tests" / "fb601_extra.js").read_text(encoding="utf-8")
EXTRA_TESTS["FB-601"] = EXTRA_TESTS["FB-601"].replace(_fb_tail, _fb_extra + _fb_tail, 1)
# Tests y descripciones de tareas viven en archivos (tests/ y tareas/) para poder editarlos sin tocar este script.
HERE = Path(__file__).resolve().parent


def _leer(carpeta, nombre):
    return (HERE / carpeta / nombre).read_text(encoding="utf-8")


UNITY_TESTS_CS = _leer("tests", "unity_tests.cs")
WEB_TESTS_JS = _leer("tests", "web_tests.js")
# Descripciones vigentes de las tareas de Unity y Web (las que no estén en tareas/ se quedan como estaban).
for _proj, _ids in (("unity", ("T-102", "T-103", "T-104")), ("web", ("W-201", "W-202", "W-203"))):
    for _id in _ids:
        PROJECTS[_proj][f"docs/tasks/{_id}.md"] = _leer("tareas", f"{_id}.md")
# Tareas retiradas del benchmark (v4): se quitan del proyecto para que el modelo no vea sus descripciones.
for _proj, _id in (("unity", "T-101"), ("web", "W-204")):
    PROJECTS[_proj].pop(f"docs/tasks/{_id}.md", None)

CATEGORIES = [
    ("unity", "Unity C#", ["T-102", "T-103", "T-104"]),
    ("web", "Web TypeScript/HTML", ["W-201", "W-202", "W-203"]),
    ("cpp", "C++ general", ["CPP-301"]),
    ("unreal", "Unreal Engine C++", ["UE-302"]),
    ("rust", "Rust", ["RS-401"]),
    ("dotnet", ".NET backend (ASP.NET Core)", ["NET-501"]),
    ("firebase", "JSON y Firebase", ["FB-601"]),
]
TASKS = [t for _, _, ts in CATEGORIES for t in ts]
TASK_CATEGORY = {t: c for c, _, ts in CATEGORIES for t in ts}
ALLOWED.update({
    "CPP-301": {"src/event_queue.hpp", "src/event_queue.cpp"},
    "UE-302": {"Source/Arena/Components/HealthComponent.h", "Source/Arena/Components/HealthComponent.cpp"},
    "RS-401": {"src/save.rs"},
    "NET-501": {"Endpoints/ScoreEndpoints.cs", "Infrastructure/InMemoryScoreRepository.cs"},
    "FB-601": {"src/migrate.ts", "firestore.rules", "firestore.indexes.json"},
})
REQUIRED = {  # archivos que deben quedar modificados/creados (los demás permitidos son opcionales)
    "CPP-301": {"src/event_queue.hpp"},
    "UE-302": {"Source/Arena/Components/HealthComponent.h", "Source/Arena/Components/HealthComponent.cpp"},
    "NET-501": {"Endpoints/ScoreEndpoints.cs", "Infrastructure/InMemoryScoreRepository.cs"},
    "FB-601": {"src/migrate.ts", "firestore.rules", "firestore.indexes.json"},
}
KINDS = {
    "unity": "un proyecto de Unity (C#)", "web": "un proyecto web en TypeScript (frontend + API)",
    "cpp": "una biblioteca en C++17", "unreal": "un módulo de juego en Unreal Engine 5 (C++)",
    "rust": "una biblioteca en Rust", "dotnet": "una API backend en ASP.NET Core (.NET)",
    "firebase": "un proyecto de datos con Firebase (TypeScript, reglas e índices de Firestore)",
}


def project_of(task):
    return TASK_CATEGORY.get(task, "web" if task.startswith("W-") else "unity")


def _allowed_ok(task, path):
    return path in ALLOWED[task]


def system_prompt(project):
    return (
        f"Eres un agente de programación que trabaja en {KINDS[project]}. Solo puedes actuar con las "
        "herramientas: list_dir, read_file, search, write_file, replace_in_file, build y finish. Antes de editar, lee los "
        "archivos que vas a tocar. Haz los cambios mínimos y correctos que pide la tarea y respeta estrictamente las "
        "convenciones del proyecto. Antes de llamar a finish, usa build y corrige los errores que reporte. Al terminar, "
        "llama a finish con un resumen.\n\n"
        "=== CONVENCIONES DEL PROYECTO (docs/CONVENTIONS.md) ===\n" + PROJECTS[project]["docs/CONVENTIONS.md"]
    )


# ----------------------------------------------------------------------------- herramientas del sistema
_TOOLS_CACHE = {}


def _run(cmd, cwd=None, env=None, timeout=300):
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -999, "TIMEOUT"
    except OSError as e:
        return -1, str(e)


def _msvc_env():
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if os.name != "nt" or not vswhere.exists():
        return None
    code, out = _run([str(vswhere), "-latest", "-products", "*", "-requires",
                      "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], timeout=60)
    path = out.strip().splitlines()[0] if code == 0 and out.strip() else ""
    vcvars = Path(path) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not path or not vcvars.exists():
        return None
    code, out = _run(f'cmd /s /c "call "{vcvars}" >nul 2>&1 && set"', timeout=120)
    env = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    return env if "INCLUDE" in env else None


def cpp_compiler():
    """('gnu', ruta) para g++/clang++, ('msvc', env) para Visual Studio, o None."""
    if "cpp" not in _TOOLS_CACHE:
        found = None
        for name in ("g++", "clang++"):
            exe = shutil.which(name)
            if exe and _run([exe, "--version"], timeout=30)[0] == 0:
                found = ("gnu", exe)
                break
        if not found:
            env = _msvc_env()
            if env:
                found = ("msvc", env)
        _TOOLS_CACHE["cpp"] = found
    return _TOOLS_CACHE["cpp"]


def cargo_path():
    if "cargo" not in _TOOLS_CACHE:
        exe = shutil.which("cargo") or (str(Path.home() / ".cargo" / "bin" / "cargo.exe") if (Path.home() / ".cargo" / "bin" / "cargo.exe").exists() else None)
        _TOOLS_CACHE["cargo"] = exe if exe and _run([exe, "--version"], timeout=60)[0] == 0 else None
    return _TOOLS_CACHE["cargo"]


def aspnet_ok():
    if "aspnet" not in _TOOLS_CACHE:
        sdk = _dotnet_sdk()
        ok = False
        if sdk:
            code, out = _run([sdk[0], "--list-runtimes"], timeout=60)
            ok = code == 0 and "Microsoft.AspNetCore.App" in out
        _TOOLS_CACHE["aspnet"] = ok
    return _TOOLS_CACHE["aspnet"]


def toolchains():
    """Estado de las herramientas por categoría: {cat: (disponible, descripción)}."""
    cc = cpp_compiler()
    cc_txt = ("g++/clang++" if cc and cc[0] == "gnu" else "MSVC (Visual Studio Build Tools)") if cc else None
    node = shutil.which("node")
    return {
        "unity": (bool(_dotnet_sdk()), "SDK de .NET" if _dotnet_sdk() else "falta el SDK de .NET"),
        "web": (True, "Node.js (tests reales)" if node else "análisis estático (instala Node.js para tests reales)"),
        "cpp": (bool(cc), cc_txt or "falta un compilador de C++"),
        "unreal": (bool(cc), (cc_txt + " + stubs de Unreal") if cc else "falta un compilador de C++"),
        "rust": (bool(cargo_path()), "cargo" if cargo_path() else "falta Rust (rustup/cargo)"),
        "dotnet": (bool(_dotnet_sdk()) and aspnet_ok(), "ASP.NET Core" if aspnet_ok() else "falta el SDK de .NET con ASP.NET Core"),
        "firebase": (True, "Node.js (tests reales)" if node else "análisis estático (instala Node.js para tests reales)"),
    }


INSTALL_HELP = {
    "cpp": "C++: instala MinGW (PowerShell como admin: choco install mingw -y) o Visual Studio Build Tools con 'Desarrollo para el escritorio con C++'.",
    "unreal": "Unreal C++: usa el mismo compilador de C++ (no necesita Unreal instalado).",
    "rust": "Rust: winget install Rustlang.Rustup  (luego abre una terminal nueva). Usa el linker de Visual Studio Build Tools.",
    "dotnet": ".NET backend: instala el SDK de .NET 8 o superior (incluye ASP.NET Core).",
    "unity": "Unity: instala el SDK de .NET 8 o superior.",
}


# ----------------------------------------------------------------------------- compilación C++
def _tmpdir(name):
    d = Path(tempfile.gettempdir()) / name
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


def _cpp_layout(root, kind):
    """Devuelve (fuentes .cpp, carpetas de include) para el proyecto."""
    root = Path(root)
    if kind == "unreal":
        gen = _tmpdir("bench_ue_generated")
        for h in (root / "Source").rglob("*.h"):
            text = h.read_text(encoding="utf-8", errors="replace")
            cls = re.search(r"class\s+(?:\w+_API\s+)?(\w+)\s*(?:final\s*)?:\s*public\s+(\w+)", text)
            body = "#pragma once\n"
            if cls:  # como en Unreal: GENERATED_BODY() declara Super y ThisClass
                body += ("#undef GENERATED_BODY\n#define GENERATED_BODY() public: using Super = %s; using ThisClass = %s; private:\n"
                         % (cls.group(2), cls.group(1)))
            for m in re.finditer(r'#include\s+"(\w+\.generated\.h)"', text):
                (gen / m.group(1)).write_text(body, encoding="utf-8")
        srcs = sorted(str(p) for p in (root / "Source").rglob("*.cpp"))
        incs = [str(root / "ThirdParty" / "UnrealStubs"), str(root / "Source" / "Arena"), str(gen)]
    else:
        srcs = sorted(str(p) for p in (root / "src").rglob("*.cpp"))
        incs = [str(root / "src")]
    return srcs, incs


def cpp_compile(sources, includes, out_exe=None, cwd=None):
    """Compila (o solo verifica si out_exe es None). Devuelve (ok, errores, warnings)."""
    cc = cpp_compiler()
    if not cc:
        return None, ["no hay compilador de C++"], []
    if cc[0] == "gnu":
        cmd = [cc[1], "-std=c++17", "-Wall", "-Wextra"] + [f"-I{i}" for i in includes] + list(sources)
        cmd += ["-o", out_exe] if out_exe else ["-fsyntax-only"]
        code, out = _run(cmd, cwd=cwd, timeout=300)
        lines = out.splitlines()
        errs = [l for l in lines if ": error:" in l or ": fatal error:" in l or "undefined reference" in l]
        warns = [l for l in lines if ": warning:" in l]
    else:
        obj = _tmpdir("bench_msvc_obj")
        envpath = next((v for k, v in cc[1].items() if k.upper() == "PATH"), "")
        cl = shutil.which("cl.exe", path=envpath) or "cl.exe"
        cmd = [cl, "/nologo", "/std:c++17", "/EHsc", "/W4", "/utf-8", "/permissive-"] + [f"/I{i}" for i in includes] + list(sources)
        cmd += [f"/Fe{out_exe}", f"/Fo{obj}\\"] if out_exe else ["/Zs"]
        code, out = _run(cmd, cwd=cwd, env=cc[1], timeout=300)
        lines = out.splitlines()
        errs = [l for l in lines if re.search(r": (fatal )?error [A-Z]+\d+", l)]
        warns = [l for l in lines if re.search(r": warning C\d+", l)]
    if code == -999:
        errs = ["la compilación tardó demasiado"]
    if code != 0 and not errs:
        errs = [l for l in lines if l.strip()][-5:] or [f"código de salida {code}"]
    return code == 0 and not errs, errs, warns


def _clean_paths(lines, root):
    r = str(Path(root))
    return [re.sub(r"^.*?[/\\](src|Source)[/\\]", r"\1/", l.replace(r + os.sep, "").replace(r + "/", "")).replace("\\", "/") for l in lines]


def build_cpp(root, kind):
    srcs, incs = _cpp_layout(root, kind)
    if not srcs:
        return "Build FALLÓ: no hay archivos .cpp"
    ok, errs, warns = cpp_compile(srcs, incs)
    if ok is None:
        return "Build no disponible: " + errs[0]
    errs, warns = _clean_paths(errs, root), _clean_paths(warns, root)
    if not ok:
        return f"Build FALLÓ (C++): {len(errs)} error(es)\n" + "\n".join(errs[:25])
    return "Build OK (C++): 0 errores." + (f" {len(warns)} warning(s):\n" + "\n".join(warns[:15]) if warns else "")


# ----------------------------------------------------------------------------- Rust
def _cargo_env():
    return dict(os.environ, CARGO_TARGET_DIR=str(Path(tempfile.gettempdir()) / "bench_cargo_target"), CARGO_TERM_COLOR="never")


def build_rust(root):
    cargo = cargo_path()
    if not cargo:
        return "Build no disponible: falta cargo"
    code, out = _run([cargo, "build", "--offline", "--message-format", "short"], cwd=root, env=_cargo_env(), timeout=600)
    errs = [l for l in out.splitlines() if re.search(r"\berror(\[E\d+\])?:", l)]
    warns = [l for l in out.splitlines() if re.search(r"\bwarning:", l) and "generated" not in l]
    if code != 0:
        return f"Build FALLÓ (cargo): {len(errs)} error(es)\n" + "\n".join((errs or out.splitlines()[-10:])[:25])
    return "Build OK (cargo): 0 errores." + (f" {len(warns)} warning(s):\n" + "\n".join(warns[:15]) if warns else "")


# ----------------------------------------------------------------------------- .NET backend
def _dotnet_copy(root, name):
    sdk = _dotnet_sdk()
    work = _tmpdir(name)
    for p in Path(root).rglob("*"):
        if p.is_file() and not any(part in ("bin", "obj") for part in p.relative_to(root).parts):
            t = work / p.relative_to(root)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, t)
    (work / "nuget.config").write_text('<?xml version="1.0" encoding="utf-8"?><configuration><packageSources><clear /></packageSources></configuration>', encoding="utf-8")
    for proj in work.glob("*.csproj"):
        txt = proj.read_text(encoding="utf-8")
        proj.write_text(re.sub(r"<TargetFramework>net\d+\.\d+</TargetFramework>", f"<TargetFramework>net{sdk[1]}.0</TargetFramework>", txt), encoding="utf-8")
    return work


def _dotnet_build(work):
    sdk = _dotnet_sdk()
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    code, out = _run([sdk[0], "build", "-nologo", "-v", "q", "-clp:NoSummary"], cwd=work, env=env, timeout=600)
    clean = lambda l: re.sub(r"\s*\[.*?\.csproj\]\s*$", "", l.replace(str(work) + os.sep, "").replace(str(work) + "/", "")).strip()
    errs = sorted({clean(l) for l in out.splitlines() if ": error " in l})
    warns = sorted({clean(l) for l in out.splitlines() if ": warning " in l})
    return code == 0 and not errs, errs or ([] if code == 0 else out.splitlines()[-5:]), warns


def build_dotnet(root):
    if not _dotnet_sdk():
        return "Build no disponible: falta el SDK de .NET"
    ok, errs, warns = _dotnet_build(_dotnet_copy(root, "bench_dotnet_build"))
    if not ok:
        return f"Build FALLÓ (dotnet): {len(errs)} error(es)\n" + "\n".join(errs[:25])
    return "Build OK (dotnet): 0 errores." + (f" {len(warns)} warning(s):\n" + "\n".join(warns[:15]) if warns else "")


# ----------------------------------------------------------------------------- Firebase / JSON
def _json_errors(root):
    errs = []
    for p in Path(root).rglob("*.json"):
        try:
            _json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            errs.append(f"{p.relative_to(root).as_posix()}: JSON inválido: {e}")
    rules = Path(root) / "firestore.rules"
    if rules.exists():
        t = rules.read_text(encoding="utf-8", errors="replace")
        if t.count("{") != t.count("}"):
            errs.append("firestore.rules: llaves desbalanceadas")
    return errs


def build_firebase(root):
    errs = _json_errors(root)
    node = shutil.which("node")
    tsc = _NODE_DEPS / "node_modules" / "typescript" / "bin" / "tsc"
    if node and tsc.exists():
        work = _tmpdir("bench_fb_build")
        shutil.copytree(Path(root) / "src", work / "work" / "src")
        (work / "tsconfig.json").write_text(TSCONFIG_JSON, encoding="utf-8")
        code, out = _run([node, str(tsc), "-p", str(work / "tsconfig.json"), "--noEmit", "--pretty", "false"], cwd=work, timeout=300)
        errs += [l.split("work/", 1)[-1].strip() for l in out.splitlines() if "error TS" in l]
        tool = "tsc estricto + validación JSON"
    else:
        res = _ts_static(Path(root))
        errs += res
        tool = "verificador TS estático + validación JSON"
    if errs:
        return f"Build FALLÓ ({tool}): {len(errs)} error(es)\n" + "\n".join(errs[:25])
    return f"Build OK ({tool}): 0 errores."


_run_build_base = run_build


def build_web_tsc(root):
    node = shutil.which("node")
    tsc = _NODE_DEPS / "node_modules" / "typescript" / "bin" / "tsc"
    if not (node and tsc.exists()):
        return None
    work = _tmpdir("bench_web_build")
    shutil.copytree(Path(root) / "src", work / "work" / "src")
    (work / "tsconfig.json").write_text(TSCONFIG_JSON, encoding="utf-8")
    code, out = _run([node, str(tsc), "-p", str(work / "tsconfig.json"), "--noEmit", "--pretty", "false"], cwd=work, timeout=300)
    errs = [l.split("work/", 1)[-1].strip() for l in out.splitlines() if "error TS" in l]
    errs += [e for e in _run_build_base(root).splitlines()[1:] if "TS1232" in e]
    if errs:
        return f"Build FALLÓ (tsc estricto): {len(errs)} error(es)\n" + "\n".join(errs[:25])
    return "Build OK (tsc estricto): 0 errores."


def run_build(root, allow_dotnet=True):
    root = Path(root)
    if (root / "Cargo.toml").exists():
        return build_rust(root)
    if list(root.glob("*.csproj")):
        return build_dotnet(root)
    if (root / "firebase.json").exists():
        return build_firebase(root)
    if (root / "ThirdParty" / "UnrealStubs").exists():
        return build_cpp(root, "unreal")
    if (root / "src").exists() and any((root / "src").rglob("*.[ch]pp")):
        return build_cpp(root, "cpp")
    if (root / "src").exists() and any((root / "src").rglob("*.ts")):
        real = build_web_tsc(root)
        if real:
            return real
    return _run_build_base(root, allow_dotnet)


# ----------------------------------------------------------------------------- tests de comportamiento
def _parse_result(out):
    m = re.search(r"@@RESULT@@(.*)", out)
    if not m:
        return None
    data = _json.loads(m.group(1))
    return {k: bool(v) for k, v in data.get("checks", {}).items()}


def tests_cpp(files, task):
    kind = "unreal" if task == "UE-302" else "cpp"
    root = _tmpdir("bench_cpp_snap")
    _write_tree(root, files)
    srcs, incs = _cpp_layout(root, kind)
    test_src = root / ("ue302_tests.cpp" if kind == "unreal" else "cpp301_tests.cpp")
    test_src.write_text(EXTRA_TESTS["UE-302" if kind == "unreal" else "CPP-301"], encoding="utf-8")
    if kind == "cpp":
        srcs = [s for s in srcs if not s.endswith("main.cpp")]
    exe = str(root / ("tests.exe" if os.name == "nt" else "tests"))
    ok, errs, warns = cpp_compile([str(test_src)] + srcs, incs, out_exe=exe, cwd=str(root))
    model_warns = [w for w in _clean_paths(warns, root) if any(a.split("/")[-1] in w for a in ALLOWED[task])]
    if not ok:
        return None, ["no compiló con los tests: " + "; ".join(_clean_paths(errs, root)[:3])], model_warns
    code, out = _run([exe], cwd=str(root), timeout=60)
    if code == -999:
        return {"termina sin colgarse": False}, ["los tests no terminaron en 60 s"], model_warns
    res = _parse_result(out)
    return (res, [], model_warns) if res is not None else (None, ["sin resultado de tests (¿crash?): " + out[-200:]], model_warns)


def tests_rust(files):
    cargo = cargo_path()
    root = _tmpdir("bench_rust_snap")
    _write_tree(root, files)
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "hidden.rs").write_text(EXTRA_TESTS["RS-401"], encoding="utf-8")
    env = _cargo_env()
    code, out = _run([cargo, "build", "--offline", "--message-format", "short"], cwd=root, env=env, timeout=600)
    warns = [l for l in out.splitlines() if re.search(r"\bwarning:", l) and "save.rs" in l]
    code, out = _run([cargo, "test", "--offline", "--test", "hidden", "--", "--test-threads=1"], cwd=root, env=env, timeout=600)
    if code == -999:
        return {"termina sin colgarse": False}, ["timeout"], warns
    tests = {m.group(1).replace("_", " "): m.group(2) == "ok" for m in re.finditer(r"^test (\w+) \.\.\. (ok|FAILED)", out, re.M)}
    if not tests:
        errs = [l for l in out.splitlines() if re.search(r"\berror(\[E\d+\])?:", l)]
        return None, ["no compiló con los tests: " + "; ".join(errs[:3] or out.splitlines()[-3:])], warns
    clippy = None
    if _run([cargo, "clippy", "--version"], timeout=60)[0] == 0:
        c2, o2 = _run([cargo, "clippy", "--offline", "--message-format", "short", "--", "-W", "clippy::all"], cwd=root, env=env, timeout=600)
        clippy = not [l for l in o2.splitlines() if "save.rs" in l and ("warning" in l or "error" in l)]
    return tests, ([] if clippy is None else [f"clippy:{clippy}"]), warns


def tests_dotnet(files):
    root = _tmpdir("bench_net_src")
    _write_tree(root, files)
    work = _dotnet_copy(root, "bench_net_tests")
    (work / "BenchHarness.cs").write_text(EXTRA_TESTS["NET-501"], encoding="utf-8")
    for proj in work.glob("*.csproj"):
        txt = proj.read_text(encoding="utf-8")
        txt = txt.replace("</PropertyGroup>", "<StartupObject>BenchHarness</StartupObject></PropertyGroup>"
                                              "<ItemGroup><Compile Remove=\"Program.cs\" /></ItemGroup>", 1)
        proj.write_text(txt, encoding="utf-8")
    ok, errs, warns = _dotnet_build(work)
    if not ok:
        return None, ["no compiló con los tests: " + "; ".join(errs[:3])], warns
    sdk = _dotnet_sdk()
    dll = next((work / "bin" / "Debug").rglob("Leaderboard.Api.dll"), None)
    if not dll:
        return None, ["no se generó el ensamblado"], warns
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", ASPNETCORE_ENVIRONMENT="Production")
    code, out = _run([sdk[0], str(dll)], cwd=str(dll.parent), env=env, timeout=180)
    if code == -999:
        return {"termina sin colgarse": False}, ["los tests no terminaron (¿bloqueo/deadlock?)"], warns
    res = _parse_result(out)
    return (res, [], warns) if res is not None else (None, ["sin resultado: " + out[-300:]], warns)


def _read_rule_ok(body):
    """read (o get + list) solo si request.auth != null."""
    rules = re.findall(r"allow\s+([\w,\s]+):\s*if\s+([^;]+);", body)
    covered = set()
    for ops, cond in rules:
        names = {o.strip() for o in ops.split(",")}
        if names & {"read", "get", "list"}:
            if not re.search(r"request\.auth\s*!=\s*null|request\.auth\.uid\s*!=\s*null", cond):
                return False
            covered |= {"get", "list"} if "read" in names else names & {"get", "list"}
    return covered == {"get", "list"}


def _rules_checks(rules):
    t = re.sub(r"//[^\n]*", "", rules or "")
    allows = re.findall(r"allow\s+([\w,\s]+):\s*if\s+([^;]+);", t)
    users = re.search(r"match\s+/users/\{(\w+)\}\s*\{(.*?)\n\s*\}", t, re.S)
    body = users.group(2) if users else ""
    var = users.group(1) if users else "uid"
    write_allows = [(ops, cond) for ops, cond in re.findall(r"allow\s+([\w,\s]+):\s*if\s+([^;]+);", body)
                    if re.search(r"\b(write|create|update)\b", ops)]
    delete_ok = not any(re.search(r"\b(write|delete)\b", ops) and cond.strip() != "false" for ops, cond in
                        re.findall(r"allow\s+([\w,\s]+):\s*if\s+([^;]+);", body))
    return {
        "reglas: rules_version '2'": bool(re.search(r"rules_version\s*=\s*['\"]2['\"]", t)),
        "reglas: sin acceso abierto (if true)": not any(c.strip() == "true" for _, c in allows),
        "reglas: lectura solo autenticados": _read_rule_ok(body),
        "reglas: escritura solo del propio usuario": bool(write_allows) and all(re.search(rf"request\.auth\.uid\s*==\s*{var}\b|{var}\s*==\s*request\.auth\.uid", c) for _, c in write_allows),
        "reglas: valida score int y displayName <= 24": bool(write_allows) and all(
            re.search(r"\.score\s+is\s+int", c) and re.search(r"displayName\s+is\s+string", c) and re.search(r"displayName\.size\(\)\s*(<=\s*24|<\s*25)", c)
            for _, c in write_allows),
        "reglas: borrar nunca": delete_ok,
        "reglas: niega todo lo demás": not re.search(r"match\s+/\{document=\*\*\}\s*\{[^}]*allow[^}]*if\s+(?!false)", t),
    }


def _index_checks(text):
    try:
        d = _json.loads(text or "")
    except Exception:
        return {"índices: JSON válido": False, "índices: users score DESC + lastLogin DESC": False, "índices: formato Firebase CLI": False}
    idx = d.get("indexes") if isinstance(d, dict) else None
    good = any(isinstance(i, dict) and i.get("collectionGroup") == "users" and i.get("queryScope") == "COLLECTION" and
               [(f.get("fieldPath"), f.get("order")) for f in i.get("fields", []) if isinstance(f, dict)] ==
               [("score", "DESCENDING"), ("lastLogin", "DESCENDING")] for i in (idx or []))
    return {"índices: JSON válido": True, "índices: users score DESC + lastLogin DESC": good,
            "índices: formato Firebase CLI": isinstance(idx, list) and isinstance(d.get("fieldOverrides", []), list)}


def _fb_static_migrate(code):
    c = _ts_nocomments(code)
    return {
        "migración: valida tipos con unknown/typeof": "typeof" in c and "unknown" in c,
        "migración: trim, nombre por defecto y recorte": ".trim()" in c and "defaultDisplayName" in c and "maxDisplayNameLength" in c,
        "migración: puntaje entero y en rango": bool(re.search(r"Number\.isInteger\(", c)) and "maxScore" in c,
        "migración: fechas a ISO": "toISOString" in c,
        "migración: inventario sin huecos (arreglo u objeto)": "Array.isArray" in c and bool(re.search(r"Object\.(keys|entries)\(", c)),
        "migración: settings 'true'/'false' a booleano": bool(re.search(r"[\"']true[\"']", c)),
        "migración: omite baneados": "banned" in c,
        "migración: entrada inválida → error users": bool(re.search(r"uid:\s*[\"']\*[\"']", c)),
    }


def tests_firebase(files, node):
    tests, notes = {}, []
    if node:
        work = _NODE_DEPS / "fbwork"
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        _write_tree(work, {k: v for k, v in files.items() if k.startswith(("src/", "data/"))})
        cfg = TSCONFIG_JSON.replace("work/src", "fbwork/src").replace("work/out", "fbwork/out")
        (_NODE_DEPS / "tsconfig_fb.json").write_text(cfg, encoding="utf-8")
        tsc = _NODE_DEPS / "node_modules" / "typescript" / "bin" / "tsc"
        _, out = _run([node, str(tsc), "-p", str(_NODE_DEPS / "tsconfig_fb.json"), "--pretty", "false"], cwd=_NODE_DEPS, timeout=300)
        ts_errors = [l for l in out.splitlines() if "error TS" in l]
        (_NODE_DEPS / "fb601_tests.js").write_text(EXTRA_TESTS["FB-601"], encoding="utf-8")
        code, out = _run([node, str(_NODE_DEPS / "fb601_tests.js"), str(work)], cwd=_NODE_DEPS, timeout=120)
        res = _parse_result(out) or {}
        tests.update({"migración: " + k: v for k, v in res.items()})
        if ts_errors:
            notes.append("tsc: " + "; ".join(e.split("fbwork/", 1)[-1] for e in ts_errors[:3]))
    else:
        tests.update(_fb_static_migrate(files.get("src/migrate.ts", "")))
    tests.update(_rules_checks(files.get("firestore.rules", "")))
    tests.update(_index_checks(files.get("firestore.indexes.json", "")))
    return tests, notes, ("tsc" if node else "")


# ----------------------------------------------------------------------------- convenciones
def _strip_c_comments(src):
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _private_fields(src):
    """Nombres de campos declarados en secciones private/protected al nivel del cuerpo de la clase."""
    names, depth, class_depth, section = [], 0, None, None
    for line in _strip_c_comments(src).splitlines():
        s = line.strip()
        if class_depth is None and re.match(r"(class|struct)\s+\w+[^;]*\{?$", s) and not s.endswith(";"):
            class_depth = depth + 1
            section = "private" if s.startswith("class") else "public"
        if class_depth is not None and depth == class_depth:
            m = re.match(r"(public|private|protected)\s*:", s)
            if m:
                section = m.group(1)
            elif section in ("private", "protected") and s.endswith(";") and "(" not in s and not s.startswith(("using", "friend", "static constexpr", "typedef")):
                fm = re.match(r".*?([A-Za-z_]\w*)\s*(=[^;]*|\{[^;]*\})?;$", s)
                if fm:
                    names.append(fm.group(1))
        depth += line.count("{") - line.count("}")
        if class_depth is not None and depth < class_depth:
            class_depth, section = None, None
    return names


def _doc_before(lines, idx):
    j = idx - 1
    while j >= 0 and (not lines[j].strip() or re.match(r"^\s*(UPROPERTY|UFUNCTION|\[\[|template|\[)", lines[j])):
        if not lines[j].strip():
            return False
        j -= 1
    return j >= 0 and (lines[j].strip().startswith("///") or lines[j].strip().endswith("*/"))


def conv_cpp301(changed, warns):
    hdr = changed.get("src/event_queue.hpp", "")
    allc = "\n".join(changed.get(p, "") for p in ALLOWED["CPP-301"])
    code = _strip_c_comments(allc)
    lines = hdr.splitlines()
    public_methods, undoc, section = [], [], "private"
    for i, l in enumerate(lines):
        s = l.strip()
        m = re.match(r"(public|private|protected)\s*:", s)
        if m:
            section = m.group(1)
            continue
        if section == "public" and "(" in s and re.match(r"^[\w:<>,\s\*&\[\]]+\s+\*?&?\w+\s*\(", s) and not s.startswith(("//", "return", "if", "for", "while")):
            public_methods.append(s)
            if not _doc_before(lines, i):
                undoc.append(s[:40])
    return {
        "#pragma once": "#pragma once" in hdr,
        "sin using namespace std en encabezado": not re.search(r"using\s+namespace\s+std", _strip_c_comments(hdr)),
        "sin new/delete/malloc": not re.search(r"\bnew\s+[A-Za-z_(]|\bdelete\s*(\[\s*\])?\s*[A-Za-z_(]|\b(malloc|free)\s*\(", code),
        "miembros privados con prefijo m_": all(n.startswith("m_") for n in _private_fields(hdr)),
        "size() const": bool(re.search(r"size\s*\(\s*\)\s*const", code)),
        "pop devuelve std::optional": bool(re.search(r"std::optional\s*<\s*(bench::)?Event\s*>\s*(EventQueue::)?pop", code)),
        "límites desde config (sin legacy ni números)": "kMaxQueuedEvents" in code and "kMinPriority" in code and "kMaxPriority" in code
        and "old_config" not in code and "MAX_EVENTS" not in code and not re.search(r"[<>=]=?\s*(8|10|16)\b", code),
        "sin printf/cout": not re.search(r"\b(printf|std::cout|cout)\b", code),
        "namespace bench": bool(re.search(r"namespace\s+bench\b", code)),
        "docs /// en métodos públicos": bool(public_methods) and not undoc,
        "compila sin warnings": not warns,
    }


def conv_ue302(changed, warns):
    h = changed.get("Source/Arena/Components/HealthComponent.h", "")
    cpp = changed.get("Source/Arena/Components/HealthComponent.cpp", "")
    code = _strip_c_comments(h + "\n" + cpp)
    includes = re.findall(r'^\s*#include\s+["<]([^">]+)[">]', h, re.M)
    hl = h.splitlines()
    macro_idx = [i for i, l in enumerate(hl) if re.match(r"\s*(UPROPERTY|UFUNCTION)\s*\(", l)]
    pub_macros, section = [], "public"
    for i, l in enumerate(hl):
        m = re.match(r"\s*(public|private|protected)\s*:", l)
        if m:
            section = m.group(1)
        if i in macro_idx and section == "public":
            pub_macros.append(i)
    bool_members = re.findall(r"^\s*bool\s+(\w+)\s*(?:=[^;]*)?;", _strip_c_comments(h), re.M)

    def macro_for(name):
        m = re.search(r"(U(?:PROPERTY|FUNCTION)\s*\(([^)]*)\))\s*\n[^\n;]*\b" + name + r"\b", h)
        return m.group(2) if m else ""
    return {
        "UCLASS con BlueprintSpawnableComponent": bool(re.search(r"UCLASS\s*\(.*BlueprintSpawnableComponent", h)),
        "GENERATED_BODY()": "GENERATED_BODY()" in h,
        ".generated.h es el último include": bool(includes) and includes[-1] == "HealthComponent.generated.h",
        "#pragma once": "#pragma once" in h,
        "UPROPERTY siempre con Category": all("Category" in m for m in re.findall(r"UPROPERTY\s*\(([^)]*)\)", h)) and "UPROPERTY" in h,
        "MaxHealth EditAnywhere / CurrentHealth VisibleAnywhere": "EditAnywhere" in macro_for("MaxHealth") and "VisibleAnywhere" in macro_for("CurrentHealth"),
        "eventos FOn... BlueprintAssignable": "BlueprintAssignable" in macro_for("OnHealthChanged") and "BlueprintAssignable" in macro_for("OnDeath")
        and bool(re.search(r"DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams\s*\(\s*FOnHealthChanged", h)),
        "UFUNCTION BlueprintCallable / BlueprintPure + const": "BlueprintCallable" in macro_for("ApplyDamage") and "BlueprintCallable" in macro_for("Heal")
        and "BlueprintPure" in macro_for("IsDead") and bool(re.search(r"IsDead\s*\(\s*\)\s*const", h)),
        "booleanos con prefijo b": all(n.startswith("b") and n[1:2].isupper() for n in bool_members),
        "sin std:: / printf / new / delete": not re.search(r"\bstd::|\b(printf|cout)\b|\bnew\s+[A-Za-z_]|\bdelete\s+[A-Za-z_]", code),
        "balance desde ArenaBalance (sin números ni Legacy)": "DefaultMaxHealth" in code
        and "Legacy" not in code and "LEGACY_" not in code and not re.search(r"\b150(\.0*)?f?\b", code),
        "docs /** */ en miembros públicos": bool(pub_macros) and all(_doc_before(hl, i) or (i > 0 and hl[i - 1].strip().endswith("*/")) for i in pub_macros),
        "compila sin warnings": not warns,
    }


def conv_rs401(changed, warns, notes):
    src = changed.get("src/save.rs", "")
    body = src.split("#[cfg(test)]")[0]
    code = re.sub(r"//[^\n]*", "", body)
    lines = body.splitlines()
    undoc = []
    for i, l in enumerate(lines):
        if re.match(r"\s*pub\s+(fn|struct|enum|const|type|trait)\b", l):
            j = i - 1
            while j >= 0 and lines[j].strip().startswith("#["):
                j -= 1
            if j < 0 or not lines[j].strip().startswith("///"):
                undoc.append(l.strip()[:40])
    c = {
        "sin unwrap/expect/panic/todo/unsafe": not re.search(r"\.unwrap\(\)|\.expect\(|\bpanic!|\btodo!|\bunimplemented!|\bunsafe\b", code),
        "límites desde config (sin legacy ni números)": all(k in code for k in ("MAX_STACK", "SAVE_VERSION"))
        and "legacy" not in code and "OLD_MAX_STACK" not in code and not re.search(r"[<>=!]=?\s*(99|20|64)\b|(==|!=)\s*2\b", code),
        "firmas públicas intactas": bool(re.search(r"pub\s+fn\s+parse_save\s*\(\s*\w+\s*:\s*&str\s*\)\s*->\s*Result<\s*SaveData\s*,\s*SaveError\s*>", code))
        and bool(re.search(r"pub\s+fn\s+to_save_string\s*\(\s*\w+\s*:\s*&SaveData\s*\)\s*->\s*String", code)),
        "/// en ítems pub": not undoc,
        "compila sin warnings": not warns,
    }
    for n in notes:
        if n.startswith("clippy:"):
            c["cargo clippy sin avisos"] = n.endswith("True")
    return c


def conv_net501(changed, warns):
    files = {k: v for k, v in changed.items() if k.endswith(".cs") and _allowed_ok("NET-501", k)}
    allc = "\n".join(files.values())
    code = re.sub(r"//[^\n]*", "", allc)
    ep = re.sub(r"//[^\n]*", "", changed.get("Endpoints/ScoreEndpoints.cs", ""))
    ns_ok = all(re.search(r"^namespace\s+Leaderboard\.Api\." + re.escape(k.split("/")[0]) + r"\s*;", v, re.M) for k, v in files.items())
    undoc = []
    for k, v in files.items():
        ls = v.splitlines()
        for i, l in enumerate(ls):
            if re.match(r"\s*public\s+(static\s+|sealed\s+|partial\s+|abstract\s+)*(class|record|interface|struct|enum)\b", l):
                j = i - 1
                while j >= 0 and ls[j].strip().startswith("["):
                    j -= 1
                if j < 0 or not ls[j].strip().startswith("///"):
                    undoc.append(l.strip()[:40])
    return {
        "sin .Result / .Wait() / GetResult()": not re.search(r"\.Result\b|\.Wait\(\)|GetAwaiter\(\)\.GetResult\(\)", code),
        "sin Console.WriteLine": "Console.Write" not in code,
        "repositorio por DI (sin new del repositorio)": not re.search(r"new\s+InMemoryScoreRepository", ep),
        "límites desde LeaderboardOptions (sin números ni Legacy)": "LeaderboardOptions" in ep and "OldLimits" not in code and "Legacy" not in code
        and not re.search(r"(?<![\w.])(50|32|1_?000_?000|100|99999)(?![\w.])", ep),
        "validación con ValidationProblem": "ValidationProblem" in ep,
        "usa los DTOs de Contracts": "SubmitScoreRequest" in ep and "ScoreResponse" in ep,
        "CancellationToken en los handlers": "CancellationToken" in ep,
        "namespace file-scoped Leaderboard.Api.<Carpeta>": bool(files) and ns_ok,
        "/// <summary> en tipos públicos": not undoc,
        "compila sin warnings": not [w for w in warns if any(Path(k).name in w for k in files)],
    }


def conv_fb601(changed):
    m = changed.get("src/migrate.ts", "")
    code = _ts_nocomments(m)
    c = {f"TS: {k}": v for k, v in web_conventions(m).items()} if m else {}
    c["esquema desde USER_SCHEMA (sin números/textos)"] = "USER_SCHEMA" in code and "Jugador" not in code and "OLD_SCHEMA" not in code \
        and not re.search(r"(?<![\w.])(24|1_?000_?000|16)(?![\w.])", code)
    c["no muta la entrada"] = not re.search(r"\bdelete\s+\w|rtdb\.\w+\s*=(?!=)|\.users\[[^\]]+\]\s*=(?!=)", code)
    c["JSON válidos"] = all(_valid_json(v) for k, v in changed.items() if k.endswith(".json"))
    return c


def _valid_json(t):
    try:
        _json.loads(t)
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------------- calificación extendida
_grade_run_base = grade_run


def grade_run(task, changed, deleted, metrics, transcript, node=None):
    if task not in ("CPP-301", "UE-302", "RS-401", "NET-501", "FB-601"):
        return _grade_run_base(task, changed, deleted, metrics, transcript, node)
    project = project_of(task)
    files = snapshot(project, changed, deleted)
    out_of_scope = sorted(k for k in changed if not _allowed_ok(task, k)) + [f"(borrado) {d}" for d in deleted]
    conv = {"solo tocó archivos permitidos": not out_of_scope,
            "creó/modificó lo pedido": all(a in changed for a in REQUIRED.get(task, ALLOWED[task]))}
    touched = any(_allowed_ok(task, k) for k in changed)
    tmp = _tmpdir("bench_agente_snap")
    _write_tree(tmp, files)
    build = run_build(tmp)
    compiles = build.startswith("Build OK")
    compile_errors = [] if compiles else build.splitlines()[1:4] or [build[:150]]
    notes, mode, tests = [], "", None
    if task in ("CPP-301", "UE-302"):
        tests, notes, warns = tests_cpp(files, task) if compiles else (None, ["no compila"], [])
        conv.update(conv_cpp301(changed, warns) if task == "CPP-301" else conv_ue302(changed, warns))
        mode = "tests reales (compilador C++)"
    elif task == "RS-401":
        tests, notes, warns = tests_rust(files) if compiles else (None, ["no compila"], [])
        conv.update(conv_rs401(changed, warns, notes))
        notes = [n for n in notes if not n.startswith("clippy:")]
        mode = "tests reales (cargo test)"
    elif task == "NET-501":
        tests, notes, warns = tests_dotnet(files) if compiles else (None, ["no compila"], [])
        conv.update(conv_net501(changed, warns))
        mode = "tests de integración HTTP reales"
    else:
        tests, notes, how = tests_firebase(files, node)
        conv.update(conv_fb601(changed))
        mode = "tests reales (Node.js) + validación de reglas/índices" if how else "análisis estático + validación de reglas/índices"
    if tests is None and compiles:
        compiles = False
        compile_errors = notes[:2]
    tests = tests or {}
    func = (sum(tests.values()) / len(tests)) if (tests and touched and (compiles or task == "FB-601")) else 0.0
    used_build = any(c.get("function", {}).get("name") == "build" for m in transcript if m.get("role") == "assistant"
                     for c in (m.get("tool_calls") or []))
    return {"task": task, "compiles": compiles, "compile_errors": compile_errors, "tests": tests, "notes": notes,
            "mode": mode, "conventions": conv, "functional": round(func, 3),
            "convention": round(sum(conv.values()) / len(conv), 3), "out_of_scope": out_of_scope,
            "used_build": used_build, "metrics": metrics}

# ============================================================================= PRUEBAS MCP (Unity y Blender simulados)
# El modelo recibe herramientas con los mismos nombres/esquemas que exponen los servidores MCP de
# Unity (Pipeline) y Blender. Las herramientas actúan sobre una escena simulada en Python y la
# calificación revisa el ESTADO FINAL y el PROCESO (inspeccionar antes de modificar, herramientas
# correctas, recuperarse de errores). No requiere Unity ni Blender instalados.
import copy as _copy

MCP_TASK_TEXT = {
    "MCP-701": """Estás conectado por MCP al Unity Editor del proyecto (escena abierta: Assets/Scenes/Level01.unity).

Arma el nivel así:
1. Un `Ground` (primitiva Plane) en posición (0, 0, 0) con escala (5, 1, 5).
2. Un objeto vacío `EnemySpawner` en posición (0, 0, 10) con el componente `EnemySpawner`; su propiedad
   `enemyPrefab` debe apuntar al prefab vigente del enemigo (búscalo en los assets; lo de `Assets/Legacy/` está obsoleto).
3. Tres objetos vacíos hijos de `EnemySpawner` llamados `SpawnPoint_1`, `SpawnPoint_2` y `SpawnPoint_3`,
   con posición LOCAL x = -4, 0 y 4 respectivamente (y = 0, z = 0).
4. Una luz `Sun`: objeto vacío con componente `Light`, propiedad `type` = `Directional` y rotación (50, -30, 0).
5. Guarda la escena.

No modifiques ni borres los objetos que ya existen en la escena. No edites archivos .unity/.prefab a mano.
Cuando termines y verifiques el resultado, llama a finish.""",
    "MCP-702": """Estás conectado por MCP a Blender con el modelo de una silla. Prepáralo para exportarlo a Unity:

1. El objeto `Cube.001` es la base de la silla: renómbralo `Chair_Base`.
2. Renombra las patas `Chair_Leg.001` … `Chair_Leg.004` a `Chair_Leg_1` … `Chair_Leg_4` (mismo orden).
3. Elimina los objetos de ayuda que están OCULTOS en el viewport. No borres la cámara ni la luz.
4. Aplica la escala de todas las piezas de la silla (que queden con escala 1 sin cambiar su tamaño visible).
5. Crea un Empty `Chair_Root` en el origen y haz que todas las piezas de la silla sean hijas de él.
6. Exporta a `//export/Chair.fbx` SOLO la silla (Chair_Root y sus piezas; sin cámara, luz ni ayudas) con
   eje adelante `-Z` y eje arriba `Y`.

`Chair_Back` ya está correcto: no cambies su transformación.
Cuando termines y verifiques el resultado, llama a finish.""",
}


def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": req}}}


_V3 = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
_FINISH = _t("finish", "Indica que terminaste la tarea, con un resumen breve.", {"summary": {"type": "string"}}, ["summary"])

UNITY_MCP_TOOLS = [
    _t("editor_status", "Estado del Unity Editor conectado (ready / safe_mode / compiling) y errores de compilación.", {}, []),
    _t("console_get_logs", "Últimos mensajes de la consola del editor (errores, warnings, logs).", {"type": {"type": "string", "enum": ["all", "error", "warning", "log"]}}, []),
    _t("editor_recompile", "Recompila los scripts del proyecto y recarga el dominio.", {}, []),
    _t("script_read", "Lee un script C# del proyecto.", {"path": {"type": "string"}}, ["path"]),
    _t("script_write", "Crea o sobrescribe un script C# del proyecto con el contenido completo.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _t("asset_find", "Busca assets por texto y tipo (prefab, material, script, scene).", {"query": {"type": "string"}, "type": {"type": "string"}}, ["query"]),
    _t("scene_get_hierarchy", "Jerarquía de la escena activa con id, nombre, transform y componentes.", {}, []),
    _t("gameobject_find", "Busca GameObjects por nombre en la escena activa.", {"name": {"type": "string"}}, ["name"]),
    _t("gameobject_create", "Crea un GameObject (vacío o primitiva).", {"name": {"type": "string"}, "primitive": {"type": "string", "enum": ["Empty", "Cube", "Sphere", "Plane", "Capsule", "Cylinder", "Quad"]}, "parentId": {"type": "integer"}}, ["name"]),
    _t("gameobject_delete", "Elimina un GameObject.", {"id": {"type": "integer"}}, ["id"]),
    _t("gameobject_set_transform", "Cambia posición/rotación/escala. space: 'local' (por defecto) o 'world'.", {"id": {"type": "integer"}, "position": _V3, "rotation": _V3, "scale": _V3, "space": {"type": "string", "enum": ["local", "world"]}}, ["id"]),
    _t("gameobject_set_parent", "Cambia el padre de un GameObject (parentId null = raíz).", {"id": {"type": "integer"}, "parentId": {"type": ["integer", "null"]}}, ["id"]),
    _t("component_add", "Agrega un componente por nombre de tipo (p. ej. Light, Rigidbody o un script).", {"id": {"type": "integer"}, "type": {"type": "string"}}, ["id", "type"]),
    _t("component_set_property", "Asigna una propiedad serializada de un componente. Para referencias a assets usa la ruta del asset.", {"id": {"type": "integer"}, "component": {"type": "string"}, "property": {"type": "string"}, "value": {}}, ["id", "component", "property", "value"]),
    _t("scene_save", "Guarda la escena activa.", {}, []),
    _t("editor_play", "Entra en Play Mode.", {}, []),
    _t("build_player", "Compila un build del juego para una plataforma.", {"target": {"type": "string"}}, ["target"]),
    _t("package_add", "Agrega un paquete UPM al proyecto.", {"name": {"type": "string"}}, ["name"]),
    _FINISH,
]

BLENDER_MCP_TOOLS = [
    _t("get_scene_info", "Resumen de la escena: objetos con tipo, transform, visibilidad y padre.", {}, []),
    _t("get_object_info", "Detalle de un objeto (transform, dimensiones, visibilidad, padre, hijos).", {"name": {"type": "string"}}, ["name"]),
    _t("execute_blender_code", "Ejecuta código Python (bpy) dentro de Blender y devuelve lo impreso o el error.", {"code": {"type": "string"}}, ["code"]),
    _t("rename_object", "Renombra un objeto.", {"name": {"type": "string"}, "new_name": {"type": "string"}}, ["name", "new_name"]),
    _t("delete_object", "Elimina un objeto.", {"name": {"type": "string"}}, ["name"]),
    _t("apply_transforms", "Aplica transformaciones (como Ctrl+A) a un objeto.", {"name": {"type": "string"}, "location": {"type": "boolean"}, "rotation": {"type": "boolean"}, "scale": {"type": "boolean"}}, ["name"]),
    _t("create_empty", "Crea un Empty.", {"name": {"type": "string"}, "location": _V3}, ["name"]),
    _t("set_parent", "Emparenta un objeto a otro conservando la transformación visual.", {"child": {"type": "string"}, "parent": {"type": "string"}}, ["child", "parent"]),
    _t("select_objects", "Selecciona objetos por nombre.", {"names": {"type": "array", "items": {"type": "string"}}, "deselect_others": {"type": "boolean"}}, ["names"]),
    _t("export_fbx", "Exporta a FBX.", {"filepath": {"type": "string"}, "use_selection": {"type": "boolean"}, "axis_forward": {"type": "string"}, "axis_up": {"type": "string"}}, ["filepath"]),
    _t("get_viewport_screenshot", "Captura del viewport.", {}, []),
    _t("add_modifier", "Agrega un modificador a un objeto.", {"name": {"type": "string"}, "type": {"type": "string"}}, ["name", "type"]),
    _t("set_material", "Asigna un material.", {"name": {"type": "string"}, "material": {"type": "string"}}, ["name", "material"]),
    _t("import_file", "Importa un archivo 3D.", {"filepath": {"type": "string"}}, ["filepath"]),
    _FINISH,
]

_SPAWNER_BROKEN = """using UnityEngine;

namespace Game.Enemies
{
    /// <summary>Genera enemigos periódicamente desde sus puntos hijos.</summary>
    public class EnemySpawner : MonoBehaviour
    {
        [SerializeField] private GameObject enemyPrefab;
        [SerializeField] private float _spawnInterval = 2f
        [SerializeField] private int _maxAlive = 4;

        private float _timer;

        private void Update()
        {
            _timer += Time.deltaTime;
            if (_timer < _spawnInterval) return;
            _timer = 0f;
            foreach (Transform point in transform)
            {
                Instantiate(enemyPrefab, point.position, Quaternion.identity);
            }
        }
    }
}
"""
_PLAYER_OK = """using UnityEngine;

namespace Game.Player
{
    /// <summary>Control básico del jugador.</summary>
    public class PlayerController : MonoBehaviour
    {
        [SerializeField] private float _speed = 5f;
    }
}
"""


def _unity_initial():
    return {
        "kind": "unity", "next_id": 3, "mods": 0, "saved_at": 0,
        "objects": {
            "1": {"name": "Main Camera", "parent": None, "primitive": "Empty", "position": [0, 1, -10], "rotation": [0, 0, 0], "scale": [1, 1, 1], "components": {"Camera": {}}},
            "2": {"name": "Ground_old", "parent": None, "primitive": "Plane", "position": [0, -5, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1], "components": {}},
        },
        "assets": ["Assets/Prefabs/Enemy.prefab", "Assets/Prefabs/Player.prefab", "Assets/Legacy/EnemyOld.prefab",
                   "Assets/Materials/Ground.mat", "Assets/Scenes/Level01.unity",
                   "Assets/Scripts/Enemies/EnemySpawner.cs", "Assets/Scripts/Player/PlayerController.cs"],
        "scripts": {"Assets/Scripts/Enemies/EnemySpawner.cs": _SPAWNER_BROKEN, "Assets/Scripts/Player/PlayerController.cs": _PLAYER_OK},
        "compiled_scripts": {"Assets/Scripts/Enemies/EnemySpawner.cs": _SPAWNER_BROKEN, "Assets/Scripts/Player/PlayerController.cs": _PLAYER_OK},
        "illegal_writes": [],
    }


def _cs_compile_errors(scripts):
    errs = []
    for path, src in scripts.items():
        code = re.sub(r"//[^\n]*", "", src)
        if code.count("{") != code.count("}"):
            errs.append(f"{path}: error CS1513: }} esperado")
        for i, line in enumerate(code.splitlines(), 1):
            s = line.strip()
            if re.match(r"^\[SerializeField\]|^(private|public|protected)\s+[\w<>\[\]]+\s+\w+\s*(=.*)?$", s) and "(" not in s and not s.endswith((";", "{", ",")):
                errs.append(f"{path}({i},{len(line) + 1}): error CS1002: ; esperado")
        m = re.search(r"class\s+(\w+)", code)
        expected = Path(path).stem
        if not m or m.group(1) != expected:
            errs.append(f"{path}: error CS0246: el nombre de la clase debe ser {expected}")
    return errs


class UnityMcpSim:
    def __init__(self):
        self.s = _unity_initial()

    def mode(self):
        return "safe_mode" if _cs_compile_errors(self.s["compiled_scripts"]) else "ready"

    def _obj(self, oid):
        o = self.s["objects"].get(str(oid))
        if o is None:
            raise ValueError(f"no existe un GameObject con id {oid}")
        return o

    def _require_ready(self):
        if self.mode() != "ready":
            raise ValueError("el editor está en Safe Mode por errores de compilación: los comandos de escena no están "
                             "disponibles (revisa editor_status o console_get_logs)")

    @staticmethod
    def _v3(v, name):
        if not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v)):
            raise TypeError(f"'{name}' debe ser un arreglo de 3 números")
        return [float(x) for x in v]

    def _mod(self):
        self.s["mods"] += 1

    def _children(self, oid):
        return [k for k, o in self.s["objects"].items() if o["parent"] == str(oid)]

    def _world_pos(self, oid):
        o = self.s["objects"][str(oid)]
        if o["parent"] is None:
            return o["position"]
        p = self._world_pos(o["parent"])
        return [a + b for a, b in zip(p, o["position"])]

    def exec(self, name, a):
        s = self.s
        if name == "editor_status":
            errs = _cs_compile_errors(s["compiled_scripts"])
            pending = s["scripts"] != s["compiled_scripts"]
            return json.dumps({"state": "safe_mode" if errs else "ready", "compileErrors": errs,
                               "scriptsChangedSinceLastCompile": pending, "activeScene": "Assets/Scenes/Level01.unity"}, ensure_ascii=False)
        if name == "console_get_logs":
            errs = _cs_compile_errors(s["compiled_scripts"])
            return json.dumps([{"type": "error", "message": e} for e in errs] or [{"type": "log", "message": "Sin errores"}], ensure_ascii=False)
        if name == "editor_recompile":
            s["compiled_scripts"] = dict(s["scripts"])
            errs = _cs_compile_errors(s["compiled_scripts"])
            return json.dumps({"success": not errs, "errors": errs, "state": "safe_mode" if errs else "ready"}, ensure_ascii=False)
        if name == "script_read":
            p = str(a["path"]).replace("\\", "/")
            if p not in s["scripts"]:
                raise ValueError(f"no existe el script '{p}'")
            return s["scripts"][p]
        if name == "script_write":
            p = str(a["path"]).replace("\\", "/")
            if not p.endswith(".cs"):
                s["illegal_writes"].append(p)
                raise ValueError("script_write solo acepta archivos .cs")
            s["scripts"][p] = str(a["content"])
            if p not in s["assets"]:
                s["assets"].append(p)
            return f"OK: escrito {p}. Recompila para aplicar los cambios."
        if name == "asset_find":
            q = str(a.get("query", "")).lower()
            typ = str(a.get("type") or "").lower()
            ext = {"prefab": ".prefab", "material": ".mat", "script": ".cs", "scene": ".unity"}.get(typ, "")
            res = [x for x in s["assets"] if q in x.lower() and x.endswith(ext)]
            return json.dumps(res)
        if name == "scene_get_hierarchy":
            self._require_ready()
            return json.dumps([{"id": int(k), **{kk: vv for kk, vv in o.items()}} for k, o in s["objects"].items()], ensure_ascii=False)
        if name == "gameobject_find":
            self._require_ready()
            n = str(a["name"])
            return json.dumps([{"id": int(k), "name": o["name"], "parent": o["parent"]} for k, o in s["objects"].items() if n.lower() in o["name"].lower()], ensure_ascii=False)
        if name == "gameobject_create":
            self._require_ready()
            prim = a.get("primitive") or "Empty"
            if prim not in ("Empty", "Cube", "Sphere", "Plane", "Capsule", "Cylinder", "Quad"):
                raise ValueError(f"primitiva desconocida '{prim}'")
            parent = a.get("parentId")
            if parent is not None:
                self._obj(parent)
            oid = str(s["next_id"])
            s["next_id"] += 1
            s["objects"][oid] = {"name": str(a["name"]), "parent": str(parent) if parent is not None else None, "primitive": prim,
                                 "position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "components": {}}
            self._mod()
            return json.dumps({"id": int(oid), "name": a["name"]})
        if name == "gameobject_delete":
            self._require_ready()
            o = self._obj(a["id"])
            for c in self._children(a["id"]):
                del s["objects"][c]
            del s["objects"][str(a["id"])]
            self._mod()
            return f"OK: eliminado {o['name']}"
        if name == "gameobject_set_transform":
            self._require_ready()
            o = self._obj(a["id"])
            space = a.get("space") or "local"
            if "position" in a and a["position"] is not None:
                pos = self._v3(a["position"], "position")
                if space == "world" and o["parent"] is not None:
                    pp = self._world_pos(o["parent"])
                    pos = [x - y for x, y in zip(pos, pp)]
                o["position"] = pos
            if a.get("rotation") is not None:
                o["rotation"] = self._v3(a["rotation"], "rotation")
            if a.get("scale") is not None:
                o["scale"] = self._v3(a["scale"], "scale")
            self._mod()
            return "OK"
        if name == "gameobject_set_parent":
            self._require_ready()
            o = self._obj(a["id"])
            p = a.get("parentId")
            if p is not None:
                self._obj(p)
            wp = self._world_pos(a["id"])
            o["parent"] = str(p) if p is not None else None
            base = self._world_pos(p) if p is not None else [0, 0, 0]
            o["position"] = [x - y for x, y in zip(wp, base)]
            self._mod()
            return "OK (posición mundial conservada)"
        if name == "component_add":
            self._require_ready()
            o = self._obj(a["id"])
            typ = str(a["type"])
            known = {"Light": {"type": "Point", "intensity": 1.0}, "Rigidbody": {}, "BoxCollider": {}, "AudioSource": {},
                     "EnemySpawner": {"enemyPrefab": None, "_spawnInterval": 2.0, "_maxAlive": 4},
                     "PlayerController": {"_speed": 5.0}, "Camera": {}}
            if typ not in known:
                raise ValueError(f"no existe el tipo de componente '{typ}'")
            o["components"][typ] = dict(known[typ])
            self._mod()
            return "OK"
        if name == "component_set_property":
            self._require_ready()
            o = self._obj(a["id"])
            comp = str(a["component"])
            if comp not in o["components"]:
                raise ValueError(f"el objeto no tiene el componente '{comp}'")
            prop = str(a["property"])
            props = o["components"][comp]
            if prop not in props:
                raise ValueError(f"'{comp}' no tiene la propiedad '{prop}'. Propiedades: {', '.join(props)}")
            val = a["value"]
            if prop == "enemyPrefab":
                if not isinstance(val, str) or val not in s["assets"] or not val.endswith(".prefab"):
                    raise ValueError(f"asset no encontrado o no es un prefab: {val}")
            if comp == "Light" and prop == "type" and val not in ("Directional", "Point", "Spot", "Area"):
                raise ValueError("Light.type debe ser Directional, Point, Spot o Area")
            props[prop] = val
            self._mod()
            return "OK"
        if name == "scene_save":
            self._require_ready()
            s["saved_at"] = s["mods"]
            return "OK: escena guardada (Assets/Scenes/Level01.unity)"
        if name == "editor_play":
            self._require_ready()
            return "OK: en Play Mode (los cambios hechos ahora se pierden al salir)"
        if name == "build_player":
            raise ValueError("no hay módulo de build instalado para esa plataforma")
        if name == "package_add":
            return "OK: paquete agregado (el proyecto se recompilará)"
        raise KeyError(name)


# ----------------------------------------------------------------------------- Blender
def _blender_initial():
    objs = {
        "o1": {"name": "Cube.001", "type": "MESH", "location": [0, 0, 0.05], "rotation": [0, 0, 0], "scale": [0.25, 0.25, 0.025], "base_dims": [2, 2, 2], "hidden": False, "parent": None},
        "o2": {"name": "Chair_Seat", "type": "MESH", "location": [0, 0, 0.5], "rotation": [0, 0, 0], "scale": [0.22, 0.22, 0.02], "base_dims": [2, 2, 2], "hidden": False, "parent": None},
        "o3": {"name": "Chair_Back", "type": "MESH", "location": [0, -0.42, 0.95], "rotation": [0, 0, 0], "scale": [1, 1, 1], "base_dims": [0.88, 0.06, 0.9], "hidden": False, "parent": None},
        "o4": {"name": "Chair_Leg.001", "type": "MESH", "location": [0.38, 0.38, 0.25], "rotation": [0, 0, 0], "scale": [0.02, 0.02, 0.25], "base_dims": [2, 2, 2], "hidden": False, "parent": None},
        "o5": {"name": "Chair_Leg.002", "type": "MESH", "location": [-0.38, 0.38, 0.25], "rotation": [0, 0, 0], "scale": [0.02, 0.02, 0.25], "base_dims": [2, 2, 2], "hidden": False, "parent": None},
        "o6": {"name": "Chair_Leg.003", "type": "MESH", "location": [0.38, -0.38, 0.25], "rotation": [0, 0, 0], "scale": [0.02, 0.02, 0.25], "base_dims": [2, 2, 2], "hidden": False, "parent": None},
        "o7": {"name": "Chair_Leg.004", "type": "MESH", "location": [-0.38, -0.38, 0.25], "rotation": [0, 0, 0], "scale": [0.02, 0.02, 0.25], "base_dims": [2, 2, 2], "hidden": False, "parent": None},
        "o8": {"name": "Camera", "type": "CAMERA", "location": [3, -3, 2], "rotation": [60, 0, 45], "scale": [1, 1, 1], "base_dims": [0, 0, 0], "hidden": False, "parent": None},
        "o9": {"name": "Light", "type": "LIGHT", "location": [2, 2, 4], "rotation": [0, 0, 0], "scale": [1, 1, 1], "base_dims": [0, 0, 0], "hidden": False, "parent": None},
        "o10": {"name": "Helper_Empty", "type": "EMPTY", "location": [0, 0, 1.5], "rotation": [0, 0, 0], "scale": [1, 1, 1], "base_dims": [0, 0, 0], "hidden": True, "parent": None},
        "o11": {"name": "Ref_Image", "type": "EMPTY", "location": [0, 2, 0.5], "rotation": [90, 0, 0], "scale": [1, 1, 1], "base_dims": [0, 0, 0], "hidden": True, "parent": None},
    }
    return {"kind": "blender", "objects": objs, "next": 12, "selected": [], "active": None, "exports": [], "code_errors": 0}


def _bl_find(state, name):
    for k, o in state["objects"].items():
        if o["name"] == name:
            return k, o
    raise ValueError(f"no existe el objeto '{name}'")


def _bl_unique(state, base):
    names = {o["name"] for o in state["objects"].values()}
    if base not in names:
        return base
    i = 1
    while f"{base}.{i:03d}" in names:
        i += 1
    return f"{base}.{i:03d}"


def _bl_info(o, state):
    dims = [round(b * s, 4) for b, s in zip(o["base_dims"], o["scale"])]
    parent = state["objects"][o["parent"]]["name"] if o["parent"] in state["objects"] else None
    children = [c["name"] for c in state["objects"].values() if c["parent"] and state["objects"].get(c["parent"]) is o]
    return {"name": o["name"], "type": o["type"], "location": o["location"], "rotation_euler_deg": o["rotation"], "scale": o["scale"],
            "dimensions": dims, "hide_viewport": o["hidden"], "parent": parent, "children": children}


FAKE_BPY_RUNNER = r'''
import json, sys, math, builtins
data = json.loads(sys.stdin.read())
S = data["state"]
out = []

class Vec(list):
    def __init__(self, owner, key):
        super().__init__(owner[key]); self._o = owner; self._k = key
    def _sync(self): self._o[self._k] = [float(v) for v in self]
    def __setitem__(self, i, v): super().__setitem__(i, v); self._sync()
    x = property(lambda s: s[0], lambda s, v: s.__setitem__(0, v))
    y = property(lambda s: s[1], lambda s, v: s.__setitem__(1, v))
    z = property(lambda s: s[2], lambda s, v: s.__setitem__(2, v))

class Obj:
    def __init__(self, oid): object.__setattr__(self, "_id", oid)
    @property
    def _d(self):
        if self._id not in S["objects"]: raise ReferenceError("StructRNA of type Object has been removed")
        return S["objects"][self._id]
    def __eq__(self, other): return isinstance(other, Obj) and other._id == self._id
    def __hash__(self): return hash(self._id)
    def __repr__(self): return f"bpy.data.objects['{self._d['name']}']"
    def __getattr__(self, k):
        d = self._d
        if k == "name": return d["name"]
        if k == "type": return d["type"]
        if k == "location": return Vec(d, "location")
        if k == "scale": return Vec(d, "scale")
        if k == "rotation_euler": return Vec(d, "rotation")
        if k == "dimensions": return [b * s for b, s in zip(d["base_dims"], d["scale"])]
        if k == "hide_viewport": return d["hidden"]
        if k == "parent": return Obj(d["parent"]) if d["parent"] in S["objects"] else None
        if k == "children": return [Obj(i) for i, o in S["objects"].items() if o["parent"] == self._id]
        if k == "users_collection": return [Collection()]
        raise AttributeError(f"'Object' object has no attribute '{k}'")
    def __setattr__(self, k, v):
        d = self._d
        if k == "name":
            names = {o["name"] for i, o in S["objects"].items() if i != self._id}
            if v in names:
                base, n = v, 1
                while f"{base}.{n:03d}" in names: n += 1
                v = f"{base}.{n:03d}"
            d["name"] = str(v)
        elif k in ("location", "scale", "rotation_euler"):
            d["rotation" if k == "rotation_euler" else k] = [float(x) for x in v]
        elif k == "hide_viewport": d["hidden"] = bool(v)
        elif k == "parent": d["parent"] = v._id if v is not None else None
        elif k == "matrix_parent_inverse": pass
        else: raise AttributeError(f"no se puede asignar '{k}' en este Blender simulado")
    def hide_get(self): return self._d["hidden"]
    def hide_set(self, v): self._d["hidden"] = bool(v)
    def select_get(self): return self._id in S["selected"]
    def select_set(self, v):
        if v and self._id not in S["selected"]: S["selected"].append(self._id)
        if not v and self._id in S["selected"]: S["selected"].remove(self._id)
    @property
    def matrix_world(self): return None

class Collection:
    objects = property(lambda s: Objects())

class Objects:
    def _ids(self): return list(S["objects"].keys())
    def __iter__(self): return iter([Obj(i) for i in self._ids()])
    def __len__(self): return len(S["objects"])
    def __getitem__(self, name):
        for i, o in S["objects"].items():
            if o["name"] == name: return Obj(i)
        raise KeyError(f'bpy_prop_collection[key]: key "{name}" not found')
    def get(self, name, default=None):
        try: return self[name]
        except KeyError: return default
    def keys(self): return [o["name"] for o in S["objects"].values()]
    def values(self): return list(self)
    def items(self): return [(o.name, o) for o in self]
    def remove(self, obj, do_unlink=True):
        oid = obj._id
        S["objects"].pop(oid, None)
        if oid in S["selected"]: S["selected"].remove(oid)
        for o in S["objects"].values():
            if o["parent"] == oid: o["parent"] = None
    def new(self, name, data):
        oid = f"o{S['next']}"; S["next"] += 1
        S["objects"][oid] = {"name": name, "type": "EMPTY" if data is None else "MESH", "location": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1], "base_dims": [0,0,0], "hidden": False, "parent": None}
        Obj(oid).name = name
        return Obj(oid)

class ViewLayerObjects:
    @property
    def active(self): return Obj(S["active"]) if S["active"] in S["objects"] else None
    @active.setter
    def active(self, v): S["active"] = v._id if v is not None else None

class _NS: pass
bpy = _NS(); bpy.data = _NS(); bpy.data.objects = Objects()
class Context:
    def __init__(self):
        self.view_layer = _NS(); self.view_layer.objects = ViewLayerObjects()
        self.scene = _NS(); self.scene.objects = Objects(); self.scene.collection = Collection()
        self.collection = Collection()
    selected_objects = property(lambda s: [Obj(i) for i in S["selected"] if i in S["objects"]])
    active_object = property(lambda s: Obj(S["active"]) if S["active"] in S["objects"] else None)
    object = property(lambda s: Obj(S["active"]) if S["active"] in S["objects"] else None)
bpy.context = Context()

class OpsObject:
    def select_all(self, action="TOGGLE"):
        if action == "DESELECT": S["selected"] = []
        elif action == "SELECT": S["selected"] = list(S["objects"].keys())
        return {"FINISHED"}
    def transform_apply(self, location=False, rotation=False, scale=False, **kw):
        for i in S["selected"]:
            o = S["objects"][i]
            if scale:
                o["base_dims"] = [b * s for b, s in zip(o["base_dims"], o["scale"])]; o["scale"] = [1.0, 1.0, 1.0]
            if location: o.setdefault("applied", []).append("location"); o["location"] = [0.0, 0.0, 0.0]
            if rotation: o.setdefault("applied", []).append("rotation"); o["rotation"] = [0.0, 0.0, 0.0]
        return {"FINISHED"}
    def delete(self, use_global=False, confirm=True):
        for i in list(S["selected"]): Objects().remove(Obj(i))
        S["selected"] = []
        return {"FINISHED"}
    def empty_add(self, type="PLAIN_AXES", location=(0, 0, 0), **kw):
        e = Objects().new("Empty", None); S["objects"][e._id]["location"] = [float(v) for v in location]
        S["selected"] = [e._id]; S["active"] = e._id
        return {"FINISHED"}
    def parent_set(self, type="OBJECT", keep_transform=False, **kw):
        if S["active"] not in S["objects"]: raise RuntimeError("Operator bpy.ops.object.parent_set.poll() failed, context is incorrect")
        for i in S["selected"]:
            if i != S["active"]: S["objects"][i]["parent"] = S["active"]
        return {"FINISHED"}
    def parent_clear(self, type="CLEAR", **kw):
        for i in S["selected"]: S["objects"][i]["parent"] = None
        return {"FINISHED"}

class OpsExport:
    def fbx(self, filepath="", use_selection=False, axis_forward="-Z", axis_up="Y", **kw):
        names = [S["objects"][i]["name"] for i in (S["selected"] if use_selection else S["objects"].keys()) if i in S["objects"]]
        S["exports"].append({"filepath": filepath, "use_selection": bool(use_selection), "axis_forward": axis_forward, "axis_up": axis_up, "objects": names, "via": "code"})
        return {"FINISHED"}

bpy.ops = _NS(); bpy.ops.object = OpsObject(); bpy.ops.export_scene = OpsExport()
bpy.ops.wm = _NS(); bpy.ops.wm.save_mainfile = lambda **kw: {"FINISHED"}
mathutils = _NS(); mathutils.Vector = lambda v: list(v)

ALLOWED = {"bpy": bpy, "math": math, "mathutils": mathutils}
def _imp(name, *a, **k):
    root = name.split(".")[0]
    if root in ALLOWED: return ALLOWED[root]
    raise ImportError(f"el módulo '{name}' no está disponible en este entorno")
safe = {k: getattr(builtins, k) for k in ("abs","all","any","bool","dict","enumerate","float","int","isinstance","len","list",
        "max","min","range","reversed","round","set","sorted","str","sum","tuple","zip","map","filter","Exception","ValueError",
        "KeyError","AttributeError","RuntimeError","ReferenceError","TypeError","ImportError","hasattr","getattr","setattr","print","repr")}
safe["print"] = lambda *a, **k: out.append(" ".join(str(x) for x in a))
safe["__import__"] = _imp
err = None
try:
    exec(data["code"], {"__builtins__": safe, "bpy": bpy, "math": math, "mathutils": mathutils})
except BaseException as e:
    import traceback
    err = f"{type(e).__name__}: {e}"
print(json.dumps({"state": S, "stdout": "\n".join(out)[-3000:], "error": err}))
'''


class BlenderMcpSim:
    def __init__(self):
        self.s = _blender_initial()

    def exec(self, name, a):
        s = self.s
        if name == "get_scene_info":
            return json.dumps({"scene": "Scene", "objects": [_bl_info(o, s) for o in s["objects"].values()]}, ensure_ascii=False)
        if name == "get_object_info":
            _, o = _bl_find(s, str(a["name"]))
            return json.dumps(_bl_info(o, s), ensure_ascii=False)
        if name == "execute_blender_code":
            try:
                r = subprocess.run([sys.executable, "-I", "-c", FAKE_BPY_RUNNER], input=json.dumps({"state": s, "code": str(a["code"])}),
                                   capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                s["code_errors"] += 1
                return "ERROR: el código tardó más de 20 s (¿bucle infinito?) y se canceló"
            try:
                res = json.loads(r.stdout.strip().splitlines()[-1])
            except Exception:
                s["code_errors"] += 1
                return "ERROR: el código no terminó correctamente: " + (r.stderr or r.stdout)[-400:]
            self.s = s = res["state"]
            if res["error"]:
                s["code_errors"] += 1
                return f"ERROR en Python: {res['error']}\n{res['stdout']}"
            return res["stdout"] or "OK (sin salida)"
        if name == "rename_object":
            k, o = _bl_find(s, str(a["name"]))
            new = str(a["new_name"])
            o["name"] = _bl_unique({"objects": {kk: oo for kk, oo in s["objects"].items() if kk != k}}, new)
            return f"OK: renombrado a {o['name']}"
        if name == "delete_object":
            k, o = _bl_find(s, str(a["name"]))
            del s["objects"][k]
            for x in s["objects"].values():
                if x["parent"] == k:
                    x["parent"] = None
            s["selected"] = [i for i in s["selected"] if i != k]
            return f"OK: eliminado {o['name']}"
        if name == "apply_transforms":
            _, o = _bl_find(s, str(a["name"]))
            if a.get("scale", True):
                o["base_dims"] = [b * sc for b, sc in zip(o["base_dims"], o["scale"])]
                o["scale"] = [1.0, 1.0, 1.0]
            if a.get("location"):
                o.setdefault("applied", []).append("location")
                o["location"] = [0.0, 0.0, 0.0]
            if a.get("rotation"):
                o.setdefault("applied", []).append("rotation")
                o["rotation"] = [0.0, 0.0, 0.0]
            return "OK"
        if name == "create_empty":
            loc = a.get("location") or [0, 0, 0]
            if not (isinstance(loc, list) and len(loc) == 3):
                raise TypeError("'location' debe ser un arreglo de 3 números")
            k = f"o{s['next']}"
            s["next"] += 1
            s["objects"][k] = {"name": _bl_unique(s, str(a["name"])), "type": "EMPTY", "location": [float(v) for v in loc],
                               "rotation": [0, 0, 0], "scale": [1, 1, 1], "base_dims": [0, 0, 0], "hidden": False, "parent": None}
            return f"OK: creado {s['objects'][k]['name']}"
        if name == "set_parent":
            kc, c = _bl_find(s, str(a["child"]))
            kp, _ = _bl_find(s, str(a["parent"]))
            if kc == kp:
                raise ValueError("un objeto no puede ser su propio padre")
            c["parent"] = kp
            return "OK"
        if name == "select_objects":
            names = a.get("names")
            if not isinstance(names, list):
                raise TypeError("'names' debe ser una lista")
            ids = [_bl_find(s, str(n))[0] for n in names]
            if a.get("deselect_others", True):
                s["selected"] = []
            for i in ids:
                if i not in s["selected"]:
                    s["selected"].append(i)
            s["active"] = ids[-1] if ids else s["active"]
            return f"OK: {len(s['selected'])} seleccionados"
        if name == "export_fbx":
            use_sel = bool(a.get("use_selection", False))
            names = [s["objects"][i]["name"] for i in (s["selected"] if use_sel else s["objects"].keys()) if i in s["objects"]]
            s["exports"].append({"filepath": str(a["filepath"]), "use_selection": use_sel, "axis_forward": a.get("axis_forward", "-Z"),
                                 "axis_up": a.get("axis_up", "Y"), "objects": names, "via": "tool"})
            return f"OK: exportados {len(names)} objetos a {a['filepath']}"
        if name == "get_viewport_screenshot":
            return "(captura no disponible en este entorno)"
        if name in ("add_modifier", "set_material"):
            _bl_find(s, str(a["name"]))
            s.setdefault("side_effects", []).append(name)
            return "OK"
        if name == "import_file":
            raise ValueError("archivo no encontrado")
        raise KeyError(name)


MCP_MAX_STEPS = 40
MCP_READ_TOOLS = {"editor_status", "console_get_logs", "script_read", "asset_find", "scene_get_hierarchy", "gameobject_find",
                  "get_scene_info", "get_object_info", "get_viewport_screenshot"}
MCP_DISTRACTORS = {"editor_play", "build_player", "package_add", "add_modifier", "set_material", "import_file"}


def run_task_mcp(base, model, task):
    sim = UnityMcpSim() if task == "MCP-701" else BlenderMcpSim()
    tools = UNITY_MCP_TOOLS if task == "MCP-701" else BLENDER_MCP_TOOLS
    names = {t["function"]["name"] for t in tools}
    app = "Unity Editor" if task == "MCP-701" else "Blender"
    msgs = [{"role": "system", "content": f"Eres un agente conectado por MCP a {app}. Solo puedes actuar con las herramientas "
             "del servidor MCP. Inspecciona el estado antes de modificar, revisa los errores que devuelvan las herramientas y "
             "corrígelos, verifica el resultado al final y llama a finish."},
            {"role": "user", "content": MCP_TASK_TEXT[task]}]
    m = {"steps": 0, "tool_calls": 0, "tool_errors": 0, "finished": False, "text_tool_leaks": 0, "error": None, "seconds": 0.0,
         "completion_tokens": 0, "max_prompt_tokens": 0, "tools_used": {}, "unknown_tools": 0, "arg_errors": 0,
         "first_modify_index": None, "first_read_index": None, "calls": []}
    t0 = time.time()
    seq = 0
    while m["steps"] < MCP_MAX_STEPS:
        if time.time() - t0 > TASK_WALL_SECONDS:
            m["error"] = "tiempo máximo por tarea agotado"
            break
        m["steps"] += 1
        try:
            resp, _ = chat(base, model, msgs, tools=tools, temperature=None)
        except Exception as e:  # noqa: BLE001
            m["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            break
        usage = resp.get("usage") or {}
        m["completion_tokens"] += usage.get("completion_tokens") or 0
        m["max_prompt_tokens"] = max(m["max_prompt_tokens"], usage.get("prompt_tokens") or 0)
        msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
        calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""
        if not calls:
            msgs.append({"role": "assistant", "content": content})
            if m["steps"] < MCP_MAX_STEPS and not m["finished"] and m["tool_calls"] == 0:
                msgs.append({"role": "user", "content": "Usa las herramientas MCP para hacer la tarea."})
                continue
            break
        fixed = []
        for c in calls:
            seq += 1
            fn = c.get("function") or {}
            fixed.append({"id": f"call_{seq}", "type": "function", "function": {"name": fn.get("name"), "arguments": fn.get("arguments") or "{}"}})
        msgs.append({"role": "assistant", "content": content, "tool_calls": fixed})
        done = False
        for c in fixed:
            name = c["function"]["name"]
            m["tool_calls"] += 1
            m["tools_used"][name] = m["tools_used"].get(name, 0) + 1
            idx = m["tool_calls"]
            m["calls"].append(name)
            if name in MCP_READ_TOOLS and m["first_read_index"] is None:
                m["first_read_index"] = idx
            if name not in MCP_READ_TOOLS and name != "finish" and m["first_modify_index"] is None:
                m["first_modify_index"] = idx
            if name == "finish":
                result, done = "OK", True
                m["finished"] = True
            elif name not in names:
                m["unknown_tools"] += 1
                result = f"ERROR: la herramienta '{name}' no existe en este servidor MCP"
            else:
                try:
                    args = json.loads(c["function"]["arguments"])
                    if not isinstance(args, dict):
                        raise ValueError("los argumentos deben ser un objeto JSON")
                    result = sim.exec(name, args)
                except (KeyError, TypeError, json.JSONDecodeError) as e:
                    m["arg_errors"] += 1
                    result = f"ERROR: argumentos inválidos para {name}: {e}"
                except Exception as e:  # noqa: BLE001
                    result = f"ERROR: {e}"
            if str(result).startswith("ERROR"):
                m["tool_errors"] += 1
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": str(result)})
        if done:
            break
    m["seconds"] = round(time.time() - t0, 1)
    return m, {"__state__.json": json.dumps(sim.s, ensure_ascii=False)}, [], msgs


def _near3(a, b, tol=0.01):
    return isinstance(a, list) and len(a) == 3 and all(abs(float(x) - y) <= tol for x, y in zip(a, b))


def grade_mcp(task, changed, metrics, transcript):
    state = json.loads(changed.get("__state__.json", "{}"))
    tests = {}
    if task == "MCP-701":
        objs = state.get("objects", {})
        by_name = {}
        for k, o in objs.items():
            by_name.setdefault(o["name"], []).append((k, o))
        one = lambda n: by_name.get(n, [(None, None)])[0] if len(by_name.get(n, [])) == 1 else (None, None)
        compiled = state.get("compiled_scripts", {}).get("Assets/Scripts/Enemies/EnemySpawner.cs", "")
        tests["arregló el error de compilación sin romper el script"] = not _cs_compile_errors(state.get("compiled_scripts", {})) \
            and "class EnemySpawner" in compiled and "enemyPrefab" in compiled and "_maxAlive" in compiled
        gk, g = one("Ground")
        tests["Ground: Plane en (0,0,0) escala (5,1,5)"] = bool(g) and g["primitive"] == "Plane" and g["parent"] is None and _near3(g["position"], [0, 0, 0]) and _near3(g["scale"], [5, 1, 5])
        sk, sp = one("EnemySpawner")
        tests["EnemySpawner en (0,0,10) con su componente"] = bool(sp) and sp["parent"] is None and _near3(sp["position"], [0, 0, 10]) and "EnemySpawner" in sp["components"]
        tests["enemyPrefab = prefab vigente (no Legacy)"] = bool(sp) and (sp["components"].get("EnemySpawner") or {}).get("enemyPrefab") == "Assets/Prefabs/Enemy.prefab"
        ok_points = True
        for i, x in ((1, -4), (2, 0), (3, 4)):
            pk, p = one(f"SpawnPoint_{i}")
            ok_points &= bool(p) and p["parent"] == sk and _near3(p["position"], [x, 0, 0])
        tests["SpawnPoint_1..3 hijos con x local -4, 0, 4"] = ok_points
        lk, light = one("Sun")
        tests["Sun: Light Directional con rotación (50,-30,0)"] = bool(light) and (light["components"].get("Light") or {}).get("type") == "Directional" and _near3(light["rotation"], [50, -30, 0])
        tests["escena guardada después del último cambio"] = state.get("mods", 0) > 0 and state.get("saved_at") == state.get("mods")
        cam, old = objs.get("1"), objs.get("2")
        keep = bool(cam) and bool(old) and _near3(old["position"], [0, -5, 0]) and cam["name"] == "Main Camera" and old["name"] == "Ground_old"
        conv = {"no tocó los objetos existentes": keep,
                "diagnosticó el Safe Mode antes de editar el script": _diag_before_write(metrics),
                "no editó escenas/prefabs a mano": not state.get("illegal_writes")}
    else:
        objs = state.get("objects", {})
        o = lambda oid: objs.get(oid)
        piece_ids = ["o1", "o2", "o3", "o4", "o5", "o6", "o7"]
        tests["Cube.001 → Chair_Base"] = bool(o("o1")) and o("o1")["name"] == "Chair_Base"
        tests["patas renombradas Chair_Leg_1..4 en orden"] = all(o(f"o{3 + i}") and o(f"o{3 + i}")["name"] == f"Chair_Leg_{i}" for i in range(1, 5))
        tests["borró las ayudas ocultas y conservó cámara y luz"] = "o10" not in objs and "o11" not in objs and "o8" in objs and "o9" in objs
        orig = _blender_initial()["objects"]

        def dims(x):
            return [b * sc for b, sc in zip(x["base_dims"], x["scale"])]
        tests["escala aplicada sin cambiar el tamaño"] = all(o(i) and _near3(o(i)["scale"], [1, 1, 1]) and _near3(dims(o(i)), dims(orig[i]), 0.001) for i in piece_ids)
        root = [(k, x) for k, x in objs.items() if x["name"] == "Chair_Root"]
        rk = root[0][0] if len(root) == 1 else None
        tests["Chair_Root en el origen con todas las piezas como hijas"] = bool(rk) and root[0][1]["type"] == "EMPTY" and _near3(root[0][1]["location"], [0, 0, 0]) \
            and all(o(i) and o(i)["parent"] == rk for i in piece_ids)
        b = o("o3")
        back_ok = bool(b) and _near3(b["location"], [0, -0.42, 0.95]) and _near3(b["scale"], [1, 1, 1]) and not b.get("applied")
        exp = (state.get("exports") or [None])[-1]
        want = {"Chair_Root", "Chair_Base", "Chair_Seat", "Chair_Back", "Chair_Leg_1", "Chair_Leg_2", "Chair_Leg_3", "Chair_Leg_4"}
        tests["exportó solo la silla a //export/Chair.fbx"] = bool(exp) and exp["filepath"].replace("\\", "/").endswith("export/Chair.fbx") and set(exp["objects"]) == want
        tests["ejes de exportación -Z adelante, Y arriba"] = bool(exp) and exp.get("axis_forward") == "-Z" and exp.get("axis_up") == "Y"
        moved_ok = all(o(i) and _near3(o(i)["location"], orig[i]["location"]) and not o(i).get("applied") for i in piece_ids)
        conv = {"código Python sin errores repetidos (≤2)": state.get("code_errors", 0) <= 2,
                "Chair_Back sin cambios de transformación": back_ok,
                "no movió piezas (ubicaciones conservadas)": moved_ok}
    conv.update({
        "inspeccionó antes de modificar": metrics.get("first_read_index") is not None and (metrics.get("first_modify_index") is None or metrics["first_read_index"] < metrics["first_modify_index"]),
        "sin herramientas inexistentes": metrics.get("unknown_tools", 0) == 0,
        "argumentos válidos (≤1 error)": metrics.get("arg_errors", 0) <= 1,
        "sin acciones innecesarias (play/build/import/…)": not any(c in MCP_DISTRACTORS for c in metrics.get("calls", [])),
        "eficiente (≤ 30 llamadas)": metrics.get("tool_calls", 0) <= 30,
        "terminó con finish": metrics.get("finished", False),
    })
    func = sum(tests.values()) / len(tests) if tests else 0.0
    conv_frac = sum(conv.values()) / len(conv) if func > 0 else 0.0
    return {"task": task, "compiles": func > 0, "compile_errors": [], "tests": tests, "notes": [], "mode": "simulación MCP (estado final + proceso)",
            "conventions": conv, "functional": round(func, 3), "convention": round(conv_frac, 3),
            "out_of_scope": [], "used_build": True, "metrics": metrics}


def _diag_before_write(m):
    calls = m.get("calls", [])
    if "script_write" not in calls:
        return False
    first_write = calls.index("script_write")
    return any(c in ("editor_status", "console_get_logs", "editor_recompile") for c in calls[:first_write])


CATEGORIES.append(("mcp", "MCP: Unity Editor y Blender", ["MCP-701", "MCP-702"]))
TASKS = [t for _, _, ts in CATEGORIES for t in ts]
TASK_CATEGORY.update({"MCP-701": "mcp", "MCP-702": "mcp"})
KINDS["mcp"] = "MCP"
_toolchains_base = toolchains


def toolchains():
    t = _toolchains_base()
    t["mcp"] = (True, "Unity MCP y Blender MCP simulados (no requieren Unity ni Blender)")
    return t


_grade_run_prev = grade_run


def grade_run(task, changed, deleted, metrics, transcript, node=None):
    if task.startswith("MCP-"):
        return grade_mcp(task, changed, metrics, transcript)
    return _grade_run_prev(task, changed, deleted, metrics, transcript, node)

# ============================================================================= EJECUCIÓN Y REPORTE (agente)
def task_score(g):
    if not g["metrics"].get("changed") and not g["metrics"].get("deleted"):
        return 0.0
    return 0.65 * g["functional"] + 0.25 * g["convention"] + 0.10 * (1.0 if g["compiles"] else 0.0)


def tool_discipline(g):
    m = g["metrics"]
    parts = [m.get("finished", False), not m.get("error"), g["used_build"], not g["out_of_scope"],
             m.get("tool_errors", 0) == 0 and m.get("text_tool_leaks", 0) == 0]
    return sum(bool(p) for p in parts) / len(parts)


def write_agent_report(path, model, speed, grades, tools, selected):
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    by_cat = {}
    for g in grades:
        by_cat.setdefault(project_of(g["task"]), []).append(g)
    cat_scores = {}
    for cat, label, _ in CATEGORIES:
        if cat in by_cat:
            cat_scores[cat] = score10(avg([task_score(g) for g in by_cat[cat]]))
    s_tools = score10(avg([tool_discipline(g) for g in grades])) if grades else None
    secs = avg([g["metrics"].get("seconds", 0) for g in grades])
    tps = speed.get("gen_tok_s") or speed.get("tok_s") or 0
    rps = speed.get("read_tok_s") or 0
    tot_tok = sum(g["metrics"].get("completion_tokens", 0) or 0 for g in grades)
    tot_sec = sum(g["metrics"].get("seconds", 0) or 0 for g in grades)
    eff = tot_tok / tot_sec if tot_sec else 0
    slow = [g for g in grades if g["metrics"].get("seconds", 0) > TARGET_SECONDS]
    tg = [g["metrics"].get("timing") or {} for g in grades]
    tg_gen = [t["gen_tok_s"] for t in tg if t.get("gen_tok_s")]
    tg_read = [t["read_tok_s"] for t in tg if t.get("read_tok_s")]
    tg_ttft = [t["avg_ttft_s"] for t in tg if t.get("avg_ttft_s") is not None]
    s_speed = score10(0.4 * clamp01((tps - 5) / 75) + 0.2 * clamp01((rps - 100) / 1400) + 0.4 * clamp01((360 - secs) / 270)) if grades else None
    code_avg = avg(list(cat_scores.values())) if cat_scores else None
    parts = [(code_avg, .70), (s_tools, .15), (s_speed, .15)]
    tot = sum(w for s, w in parts if s is not None)
    overall = round(sum(s * w for s, w in parts if s is not None) / tot, 1) if tot else None
    L = ["=" * 80, "  CALIFICACIÓN — ROL AGENTE (programación con herramientas)", "=" * 80,
         f"  Modelo:        {model.get('id')}",
         f"  Cuantización:  {model.get('quantization', '?')}    Contexto cargado: {model.get('loaded_context_length', '?')}",
         f"  Fecha:         {datetime.datetime.now():%Y-%m-%d %H:%M}",
         f"  Ejecuciones:   {len(grades)} (tareas × intentos)    Benchmark: {BENCH_VERSION}",
         f"  Velocidad:     lectura {rps:.0f} tok/s · generación {tps:.1f} tok/s · efectiva en tareas {eff:.0f} tok/s",
         *( [f"  En tareas:     generación {avg(tg_gen):.1f} tok/s (promedio de intentos)"] if tg_gen else []),
         f"  Tiempo:        {secs:.0f} s promedio por tarea (objetivo ≤ {TARGET_SECONDS} s) · tareas de más de 3 min: {len(slow)}/{len(grades)}", "",
         f"  CALIFICACIÓN GLOBAL: {overall if overall is not None else 'N/A'} / 10", "",
         "  ÁREAS DE CÓDIGO", "  " + "-" * 76]
    for cat, label, tasks in CATEGORIES:
        if cat in cat_scores:
            L.append(bar(f"{label} ({', '.join(tasks)})", cat_scores[cat], 64))
        elif cat in selected:
            L.append(f"  {label}: N/A — {tools[cat][1]}")
    L += ["", "  PROCESOS", "  " + "-" * 76,
          bar("Promedio de áreas de código", round(code_avg, 1) if code_avg is not None else None, 64),
          bar("Uso de herramientas (termina, usa build, alcance, sin errores)", s_tools, 64),
          bar(f"Velocidad (lectura, generación y tiempo por tarea)", s_speed, 64), "",
          "  Cada tarea: 65% comportamiento (tests) + 25% convenciones + 10% compila.",
          "  Global: promedio de áreas 70% + herramientas 15% + velocidad 15%.",
          "  Velocidad: 40% generación + 20% lectura + 40% tiempo por tarea (10 si ≤ 90 s, 1 si ≥ 360 s).", "",
          "  CÓMO SE VERIFICÓ CADA ÁREA", "  " + "-" * 76]
    for cat, label, _ in CATEGORIES:
        if cat in by_cat:
            L.append(f"  {label}: {by_cat[cat][0].get('mode') or tools[cat][1]}")
    L += ["", "  DETALLE POR TAREA", "  " + "-" * 76]
    for g in grades:
        m = g["metrics"]
        t_ok = sum(g["tests"].values())
        c_ok = sum(g["conventions"].values())
        L.append(f"  {g['task']} intento {g['run']}:  {score10(task_score(g)):4.1f}/10   compila {'✓' if g['compiles'] else '✗'}"
                 f" | comportamiento {t_ok}/{len(g['tests'])} | convenciones {c_ok}/{len(g['conventions'])}"
                 f" | {m.get('seconds', 0):.0f} s{' ⏱' if m.get('seconds', 0) > TARGET_SECONDS else ''}, {m.get('steps', 0)} pasos,"
                 + (f" {timing_text(m['timing'])}" if (m.get('timing') or {}).get('gen_tok_s') else
                    f" {(m.get('completion_tokens') or 0) / max(1, m.get('seconds', 0) or 1):.0f} tok/s"))
        for e in g["compile_errors"][:2]:
            L.append(f"      ✗ compilación: {str(e)[:110]}")
        for k, v in g["tests"].items():
            if not v:
                L.append(f"      ✗ {k}")
        for k, v in g["conventions"].items():
            if not v:
                L.append(f"      ✗ convención: {k}")
        for n in g.get("notes", [])[:2]:
            if n and "no compila" not in n:
                L.append(f"      · {str(n)[:110]}")
        if m.get("error"):
            L.append(f"      ⚠ {str(m['error'])[:110]}")
        if not g["used_build"]:
            L.append("      · no usó la herramienta build para verificar")
    L += ["", "  Escala: 10 = perfecto · 7-9 = usable con revisión · 4-6 = requiere corrección frecuente · 1-3 = no apto", ""]
    text = "\n".join(L)
    Path(path).write_text(text, encoding="utf-8")
    return text, overall


def main():
    cats = [c for c, _, _ in CATEGORIES]
    ap = argparse.ArgumentParser(description="Benchmark del rol AGENTE (código con herramientas).")
    add_backend_args(ap)
    ap.add_argument("--modelo", help="id (o parte) del modelo; por defecto el que esté cargado")
    ap.add_argument("--intentos", type=int, default=1, help="intentos por tarea (por defecto 1)")
    ap.add_argument("--categorias", nargs="*", choices=cats, help="categorías a probar (por defecto todas): " + " ".join(cats))
    ap.add_argument("--tareas", nargs="*", help="ids de tareas concretas (p. ej. UE-302 RS-401)")
    ap.add_argument("--repetir", action="store_true", help="ignorar resultados guardados y rehacer todo")
    ap.add_argument("--rapido", action="store_true", help="1 intento y una sola tarea representativa por categoría")
    args = ap.parse_args()
    if args.rapido:
        args.intentos = 1
    base = prepare_backend(args)
    here = Path(__file__).resolve().parent
    print("=" * 74 + "\n BENCHMARK AGENTE — Unity, Web, C++, Unreal, Rust, .NET, JSON/Firebase y MCP\n" + "=" * 74)
    model = choose_model(base, args.modelo)
    mid = model["id"]
    out = here / "resultados_agente" / safe_name(mid) / BENCH_VERSION
    out.mkdir(parents=True, exist_ok=True)
    sys.stdout = Tee(sys.stdout, out / "log.txt")
    node = node_ready()
    tools = toolchains()
    selected = args.categorias or cats
    print("\nHerramientas para calificar:")
    for cat, label, _ in CATEGORIES:
        if cat in selected:
            ok, desc = tools[cat]
            print(f"  {'✓' if ok else '✗'} {label:30} {desc}")
    missing = [c for c in selected if not tools[c][0]]
    if missing:
        print("\nÁreas que se omiten por falta de herramientas (aparecerán como N/A):")
        for c in missing:
            print("  - " + INSTALL_HELP.get(c, c))
    run_cats = [c for c in selected if tools[c][0]]
    tasks = args.tareas or ([QUICK_TASKS[c] for c in run_cats] if args.rapido else [t for c, _, ts in CATEGORIES if c in run_cats for t in ts])
    print(f"\nVelocidad…", end=" ", flush=True)
    speed = measure_speed(base, mid)
    print(speed_line(speed))
    print(f"Tareas: {', '.join(tasks)} × {args.intentos} intento(s)\n")
    grades = []
    for task in tasks:
        for run in range(1, args.intentos + 1):
            f = out / f"{task}_intento{run}.json"
            if f.exists() and not args.repetir:
                data = json.loads(f.read_text(encoding="utf-8"))
                grades.append(data["grade"])
                print(f"  · {task} intento {run}: ya estaba hecho ({score10(task_score(data['grade']))}/10)")
                continue
            print(f"  · {task} intento {run}…", end=" ", flush=True)
            del _TIMING[:]
            runner = run_task_mcp if task.startswith("MCP-") else run_task
            metrics, changed, deleted, transcript = runner(base, mid, task) if task.startswith("MCP-") else runner(base, mid, task, temperature=None)
            metrics["changed"], metrics["deleted"] = sorted(changed), deleted
            metrics["timing"] = timing_summary(_TIMING)
            try:
                g = grade_run(task, changed, deleted, metrics, transcript, node)
            except Exception as e:  # noqa: BLE001
                g = {"task": task, "compiles": False, "compile_errors": [f"error del calificador: {e}"], "tests": {},
                     "notes": [], "mode": "", "conventions": {}, "functional": 0.0, "convention": 0.0,
                     "out_of_scope": [], "used_build": False, "metrics": metrics}
            g["run"] = run
            grades.append(g)
            f.write_text(json.dumps({"grade": g, "files": changed, "transcript": transcript}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
            tt = timing_text(metrics.get("timing") or {})
            print(f"{'✓ OK' if task_score(g) >= 0.7 else ('~ parcial' if task_score(g) >= 0.4 else '✗ error')} "
                  f"{score10(task_score(g))}/10  ({metrics['seconds']} s{' ⏱ más de 3 min' if metrics['seconds'] > TARGET_SECONDS else ''}, {metrics['steps']} pasos"
                  + (f", ⚠ {metrics['error']}" if metrics.get("error") else "") + ")"
                  + (f"\n      velocidad: {tt}" if tt else ""))
    report = here / f"calificacion_agente_{safe_name(mid)}_{datetime.datetime.now():%Y%m%d-%H%M}.txt"
    text, overall = write_agent_report(report, model, speed, grades, tools, selected)
    print("\n" + text)
    print(f"Reporte guardado en: {report}")


if __name__ == "__main__":
    main()
