using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Launcher {
    [STAThread]
    static int Main(string[] args) {
        try {
            string app = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(app, "runtime", "pythonw.exe");
            string main = Path.Combine(app, "main.py");
            if (!File.Exists(python) || !File.Exists(main)) throw new IOException("بسته کامل نیست؛ ZIP را دوباره در یک پوشه استخراج کنید.");
            var info = new ProcessStartInfo(python);
            info.Arguments = Quote(main);
            foreach (string arg in args) info.Arguments += " " + Quote(arg);
            info.WorkingDirectory = app;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            var process = Process.Start(info);
            process.WaitForExit();
            return process.ExitCode;
        } catch (Exception e) {
            MessageBox.Show("راه‌اندازی ممکن نشد.\n" + e.Message, "سیستم مطالعه من", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
    // Windows command-line quoting, including paths ending in a backslash.
    static string Quote(string value) {
        var result = new System.Text.StringBuilder("\"");
        int slashes = 0;
        foreach (char ch in value) {
            if (ch == '\\') { slashes++; continue; }
            if (ch == '"') result.Append('\\', slashes * 2 + 1);
            else result.Append('\\', slashes);
            result.Append(ch); slashes = 0;
        }
        result.Append('\\', slashes * 2);
        result.Append('"');
        return result.ToString();
    }
}
