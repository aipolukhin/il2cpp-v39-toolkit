using System;
namespace Il2CppDumper
{
    public static class MainForm
    {
        public static void Log(string msg, params object[] args)
        {
            try { Console.WriteLine(args != null && args.Length > 0 && msg.Contains("{") ? string.Format(msg, args) : msg); }
            catch { Console.WriteLine(msg); }
        }
    }
    public class Brush { }
    public static class Brushes
    {
        public static readonly Brush Orange = new Brush();
        public static readonly Brush Yellow = new Brush();
        public static readonly Brush Lime = new Brush();
        public static readonly Brush LightGreen = new Brush();
        public static readonly Brush Chartreuse = new Brush();
        public static readonly Brush Red = new Brush();
    }
}
