
using System;
using System.Diagnostics;
using System.IO;
class Program {
    static int Main(string[] args) {
        try { File.AppendAllText(@"c:\\Projetos\\teste\\pwsh_log.txt", DateTime.Now.ToString("o") + " | " + string.Join(" ", args) + Environment.NewLine); } catch { }
        if (args.Length == 1 && args[0] == "--version") {
            Console.WriteLine("7.0.0");
            return 0;
        }
        var psi = new ProcessStartInfo();
        psi.FileName = "powershell.exe";
        if (args.Length > 0) {
            psi.Arguments = string.Join(" ", args);
        }
        psi.UseShellExecute = false;
        var p = Process.Start(psi);
        p.WaitForExit();
        return p.ExitCode;
    }
}
