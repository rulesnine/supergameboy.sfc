using System;
using System.Drawing;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;
using System.Reflection;

[assembly: AssemblyTitle("Ik Core SGBPACK Builder")]
[assembly: AssemblyDescription("SGBPACK1 builder for Ik Core")]
[assembly: AssemblyCompany("Ik Core Project")]
[assembly: AssemblyProduct("Ik Core SGBPACK Builder")]
[assembly: AssemblyCopyright("Ik Core modifications 2026")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace IkCoreSGBPackBuilder
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }

    internal sealed class MainForm : Form
    {
        private readonly TextBox sgbBox = new TextBox();
        private readonly TextBox gbBox = new TextBox();
        private readonly TextBox bootBox = new TextBox();
        private readonly TextBox outBox = new TextBox();
        private readonly TextBox statusBox = new TextBox();

        public MainForm()
        {
            Text = "Ik Core SGBPACK Builder v1.0";
            ClientSize = new Size(760, 415);
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = true;

            var title = new Label {
                Text = "Ik Core SGBPACK Builder",
                Font = new Font("Segoe UI", 14, FontStyle.Bold),
                AutoSize = true,
                Location = new Point(20, 15)
            };
            Controls.Add(title);

            var sub = new Label {
                Text = "Crea archivos SGBPACK1 para Ik Core. No incluye ROMs ni BIOS.",
                AutoSize = true,
                Location = new Point(22, 49)
            };
            Controls.Add(sub);

            AddFileRow("Programa SGB (.sfc):", 90, sgbBox,
                "ROM SNES/SGB (*.sfc;*.smc)|*.sfc;*.smc|Todos los archivos (*.*)|*.*");
            AddFileRow("Juego Game Boy:", 135, gbBox,
                "ROM Game Boy (*.gb;*.gbc)|*.gb;*.gbc|Todos los archivos (*.*)|*.*");
            AddFileRow("Boot ROM SGB (256 B):", 180, bootBox,
                "Boot ROM (*.rom;*.bin)|*.rom;*.bin|Todos los archivos (*.*)|*.*");

            var outLabel = new Label {
                Text = "Salida SGBPACK:",
                Location = new Point(20, 229),
                Size = new Size(145, 22)
            };
            Controls.Add(outLabel);
            outBox.Location = new Point(165, 225);
            outBox.Size = new Size(480, 24);
            Controls.Add(outBox);

            var saveButton = new Button {
                Text = "Guardar...",
                Location = new Point(655, 224),
                Size = new Size(80, 27)
            };
            saveButton.Click += (s, e) => {
                using (var dlg = new SaveFileDialog()) {
                    dlg.Filter = "SGBPACK (*.sfc)|*.sfc|Todos los archivos (*.*)|*.*";
                    dlg.FileName = "Juego_SGBPACK_v1.sfc";
                    if (dlg.ShowDialog(this) == DialogResult.OK)
                        outBox.Text = dlg.FileName;
                }
            };
            Controls.Add(saveButton);

            statusBox.Location = new Point(20, 275);
            statusBox.Size = new Size(715, 70);
            statusBox.Multiline = true;
            statusBox.ReadOnly = true;
            statusBox.ScrollBars = ScrollBars.Vertical;
            statusBox.Text = "Ik Core Builder listo. Selecciona los tres componentes y una ruta de salida.";
            Controls.Add(statusBox);

            var build = new Button {
                Text = "CREAR SGBPACK1",
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Location = new Point(565, 355),
                Size = new Size(170, 35)
            };
            build.Click += BuildClicked;
            Controls.Add(build);
        }

        private void AddFileRow(string labelText, int y, TextBox box, string filter)
        {
            var lab = new Label {
                Text = labelText,
                Location = new Point(20, y + 4),
                Size = new Size(145, 22)
            };
            Controls.Add(lab);

            box.Location = new Point(165, y);
            box.Size = new Size(480, 24);
            Controls.Add(box);

            var button = new Button {
                Text = "Examinar...",
                Location = new Point(655, y - 1),
                Size = new Size(80, 27)
            };
            button.Click += (s, e) => {
                using (var dlg = new OpenFileDialog()) {
                    dlg.Filter = filter;
                    if (dlg.ShowDialog(this) == DialogResult.OK)
                        box.Text = dlg.FileName;
                }
            };
            Controls.Add(button);
        }

        private void BuildClicked(object sender, EventArgs e)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(sgbBox.Text) ||
                    string.IsNullOrWhiteSpace(gbBox.Text) ||
                    string.IsNullOrWhiteSpace(bootBox.Text) ||
                    string.IsNullOrWhiteSpace(outBox.Text))
                    throw new InvalidOperationException("Falta seleccionar uno o más archivos.");

                statusBox.Text = "Construyendo y verificando...";
                Refresh();

                BuildResult r = SgbPack.Build(sgbBox.Text, gbBox.Text, bootBox.Text, outBox.Text);
                statusBox.Text = string.Format(
                    "SGBPACK creado correctamente.\r\nTítulo GB: {0} | SGB: {1} B | GB: {2} B | Boot: {3} B | Total: {4} B | SGB flag: 0x{5:X2}",
                    r.Title, r.SgbBytes, r.GbBytes, r.BootBytes, r.TotalBytes, r.SgbFlag);
                if (!string.IsNullOrEmpty(r.Note))
                    statusBox.AppendText("\r\n" + r.Note);

                MessageBox.Show(this, "SGBPACK1 creado y verificado correctamente.",
                    "Ik Core SGBPACK Builder", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                statusBox.Text = "ERROR: " + ex.Message;
                MessageBox.Show(this, ex.Message, "Ik Core SGBPACK Builder",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }

    internal sealed class BuildResult
    {
        public string Title;
        public int SgbBytes;
        public int GbBytes;
        public int BootBytes;
        public long TotalBytes;
        public byte SgbFlag;
        public string Note;
    }

    internal static class SgbPack
    {
        private static readonly byte[] NintendoLogo = {
            0xCE,0xED,0x66,0x66,0xCC,0x0D,0x00,0x0B,0x03,0x73,0x00,0x83,0x00,0x0C,0x00,0x0D,
            0x00,0x08,0x11,0x1F,0x88,0x89,0x00,0x0E,0xDC,0xCC,0x6E,0xE6,0xDD,0xDD,0xD9,0x99,
            0xBB,0xBB,0x67,0x63,0x6E,0x0E,0xEC,0xCC,0xDD,0xDC,0x99,0x9F,0xBB,0xB9,0x33,0x3E
        };

        private static readonly byte[] BootSignature = {
            0x31,0xFE,0xFF,0x3E,0x30,0xE0,0x00,0xAF,0x21,0xFF,0x9F,0x32,0xCB,0x7C,0x20,0xFB
        };

        public static BuildResult Build(string sgbPath, string gbPath, string bootPath, string outPath)
        {
            if (!File.Exists(sgbPath)) throw new FileNotFoundException("No se encontró la ROM del programa SGB.");
            if (!File.Exists(gbPath)) throw new FileNotFoundException("No se encontró la ROM de Game Boy.");
            if (!File.Exists(bootPath)) throw new FileNotFoundException("No se encontró la boot ROM SGB.");

            byte[] sgb = File.ReadAllBytes(sgbPath);
            byte[] gb = File.ReadAllBytes(gbPath);
            byte[] boot = File.ReadAllBytes(bootPath);

            if (sgb.Length < 32768)
                throw new InvalidDataException("La ROM SGB seleccionada es demasiado pequeña.");
            ValidateGameBoy(gb);
            if (boot.Length != 256)
                throw new InvalidDataException("La boot ROM SGB debe medir exactamente 256 bytes.");

            string note = null;
            bool bootMatches = true;
            for (int i = 0; i < BootSignature.Length; i++)
                if (boot[i] != BootSignature[i]) { bootMatches = false; break; }
            if (!bootMatches)
                note = "Advertencia: la boot ROM mide 256 bytes, pero su firma inicial no coincide con la referencia SGB usada en el proyecto.";

            uint sgbOff = 0;
            uint sgbSize = checked((uint)sgb.Length);
            uint gbOff = sgbSize;
            uint gbSize = checked((uint)gb.Length);
            uint bootOff = checked(gbOff + gbSize);
            uint bootSize = checked((uint)boot.Length);

            byte[] payload = new byte[checked(sgb.Length + gb.Length + boot.Length)];
            Buffer.BlockCopy(sgb, 0, payload, 0, sgb.Length);
            Buffer.BlockCopy(gb, 0, payload, checked((int)gbOff), gb.Length);
            Buffer.BlockCopy(boot, 0, payload, checked((int)bootOff), boot.Length);

            byte[] footer = new byte[256];
            Buffer.BlockCopy(Encoding.ASCII.GetBytes("SGBPACK1"), 0, footer, 0, 8);
            PutU32(footer, 0x08, 1);
            PutU32(footer, 0x0C, 1);
            PutU32(footer, 0x10, sgbOff);
            PutU32(footer, 0x14, sgbSize);
            PutU32(footer, 0x18, gbOff);
            PutU32(footer, 0x1C, gbSize);
            PutU32(footer, 0x20, bootOff);
            PutU32(footer, 0x24, bootSize);
            PutU32(footer, 0x28, Crc32(sgb));
            PutU32(footer, 0x2C, Crc32(gb));
            PutU32(footer, 0x30, Crc32(boot));

            footer[0x34] = gb[0x147];
            footer[0x35] = gb[0x148];
            footer[0x36] = gb[0x149];
            footer[0x37] = gb[0x146];

            byte[] title = Encoding.ASCII.GetBytes(GetTitle(gb));
            Buffer.BlockCopy(title, 0, footer, 0x38, Math.Min(16, title.Length));

            Buffer.BlockCopy(Sha256(gb), 0, footer, 0x48, 32);
            Buffer.BlockCopy(Sha256(sgb), 0, footer, 0x68, 32);
            Buffer.BlockCopy(Sha256(boot), 0, footer, 0x88, 32);
            PutU32(footer, 0xA8, Crc32(payload));

            string dir = Path.GetDirectoryName(Path.GetFullPath(outPath));
            if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);

            using (var fs = new FileStream(outPath, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                fs.Write(payload, 0, payload.Length);
                fs.Write(footer, 0, footer.Length);
            }

            Verify(outPath, payload.Length, gbOff, bootOff);

            return new BuildResult {
                Title = GetTitle(gb),
                SgbBytes = sgb.Length,
                GbBytes = gb.Length,
                BootBytes = boot.Length,
                TotalBytes = new FileInfo(outPath).Length,
                SgbFlag = gb[0x146],
                Note = note
            };
        }

        private static void ValidateGameBoy(byte[] gb)
        {
            if (gb.Length < 0x150)
                throw new InvalidDataException("La ROM de Game Boy es demasiado pequeña.");

            for (int i = 0; i < NintendoLogo.Length; i++)
                if (gb[0x104 + i] != NintendoLogo[i])
                    throw new InvalidDataException("La cabecera no parece ser una ROM Game Boy válida.");

            int x = 0;
            for (int i = 0x134; i <= 0x14C; i++)
                x = (x - gb[i] - 1) & 0xFF;
            if ((byte)x != gb[0x14D])
                throw new InvalidDataException("La ROM Game Boy tiene checksum de cabecera inválido.");
        }

        private static string GetTitle(byte[] gb)
        {
            if (gb.Length < 0x150) return "";
            string s = Encoding.ASCII.GetString(gb, 0x134, 16);
            return s.Trim('\0', ' ');
        }

        private static byte[] Sha256(byte[] data)
        {
            using (SHA256 sha = SHA256.Create())
                return sha.ComputeHash(data);
        }

        private static uint Crc32(byte[] data)
        {
            uint crc = 0xFFFFFFFFu;
            foreach (byte b in data)
            {
                crc ^= b;
                for (int i = 0; i < 8; i++)
                    crc = ((crc & 1u) != 0) ? ((crc >> 1) ^ 0xEDB88320u) : (crc >> 1);
            }
            return crc ^ 0xFFFFFFFFu;
        }

        private static void PutU32(byte[] b, int off, uint value)
        {
            byte[] t = BitConverter.GetBytes(value);
            Buffer.BlockCopy(t, 0, b, off, 4);
        }

        private static uint GetU32(byte[] b, int off)
        {
            return BitConverter.ToUInt32(b, off);
        }

        private static void Verify(string path, int payloadLength, uint expectedGbOff, uint expectedBootOff)
        {
            byte[] all = File.ReadAllBytes(path);
            if (all.Length != payloadLength + 256)
                throw new InvalidDataException("La verificación final falló: tamaño incorrecto.");

            int f = all.Length - 256;
            if (Encoding.ASCII.GetString(all, f, 8) != "SGBPACK1")
                throw new InvalidDataException("La verificación final falló: firma SGBPACK1 ausente.");
            if (GetU32(all, f + 0x18) != expectedGbOff)
                throw new InvalidDataException("La verificación final falló: offset GB incorrecto.");
            if (GetU32(all, f + 0x20) != expectedBootOff)
                throw new InvalidDataException("La verificación final falló: offset boot incorrecto.");

            byte[] payload = new byte[payloadLength];
            Buffer.BlockCopy(all, 0, payload, 0, payloadLength);
            if (Crc32(payload) != GetU32(all, f + 0xA8))
                throw new InvalidDataException("La verificación final falló: CRC del payload no coincide.");
        }
    }
}
