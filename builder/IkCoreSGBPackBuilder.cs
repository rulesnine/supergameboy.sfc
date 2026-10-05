using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;
using System.Reflection;

[assembly: AssemblyTitle("Ik Core SGBPACK Builder")]
[assembly: AssemblyDescription("SGBPACK1 builder for Ik Core")]
[assembly: AssemblyCompany("Ik Core Project")]
[assembly: AssemblyProduct("Ik Core SGBPACK Builder")]
[assembly: AssemblyCopyright("Ik Core modifications 2026")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

namespace IkCoreSGBPackBuilder
{
    internal static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [STAThread]
        private static void Main(string[] args)
        {
            try { SetProcessDPIAware(); } catch { }

            if (args != null && Array.Exists(args, delegate(string a) {
                return string.Equals(a, "--self-test-logo", StringComparison.OrdinalIgnoreCase);
            }))
            {
                using (Bitmap testLogo = MainForm.LoadApprovedIkCoreBitmap())
                {
                    Environment.Exit(testLogo != null && testLogo.Width > 0 && testLogo.Height > 0 ? 0 : 10);
                }
                return;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }

    internal sealed class RoundedButton : Button
    {
        public int CornerRadius = 8;

        public RoundedButton()
        {
            FlatStyle = FlatStyle.Flat;
            FlatAppearance.BorderSize = 0;
            BackColor = Color.FromArgb(0, 120, 215);
            ForeColor = Color.White;
            Cursor = Cursors.Hand;
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            using (GraphicsPath p = new GraphicsPath())
            {
                int r = CornerRadius * 2;
                Rectangle rect = new Rectangle(0, 0, Width, Height);
                p.AddArc(rect.X, rect.Y, r, r, 180, 90);
                p.AddArc(rect.Right - r, rect.Y, r, r, 270, 90);
                p.AddArc(rect.Right - r, rect.Bottom - r, r, r, 0, 90);
                p.AddArc(rect.X, rect.Bottom - r, r, r, 90, 90);
                p.CloseFigure();
                Region = new Region(p);
            }
        }
    }

    internal sealed class MainForm : Form
    {
        private readonly TextBox gbBox = CreateInputBox();
        private readonly TextBox sgbBox = CreateInputBox();
        private readonly TextBox bootBox = CreateInputBox();
        private readonly TextBox titleBox = CreateInputBox();
        private readonly TextBox idBox = CreateInputBox();
        private readonly ComboBox regionBox = new ComboBox();
        private readonly CheckBox includeBoot = new CheckBox();
        private readonly CheckBox validateImage = new CheckBox();
        private readonly CheckBox optimizeSize = new CheckBox();
        private readonly Label statusLabel = new Label();
        private readonly Panel progressTrack = new Panel();
        private readonly Panel progressFill = new Panel();
        private string lastOutputPath = "";

        private static Icon LoadEmbeddedIkCoreIcon()
        {
            try
            {
                using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream("IkCoreLogo.ico"))
                {
                    if (s == null) return null;
                    using (Icon src = new Icon(s))
                        return (Icon)src.Clone();
                }
            }
            catch { return null; }
        }

        internal static Bitmap LoadApprovedIkCoreBitmap()
        {
            try
            {
                using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream("IkCoreLogo.png"))
                {
                    if (s == null) return null;
                    using (Image src = Image.FromStream(s, true, true))
                        return new Bitmap(src);
                }
            }
            catch { return null; }
        }

        private static TextBox CreateInputBox()
        {
            return new TextBox {
                Font = new Font("Segoe UI", 9.5f, FontStyle.Regular),
                BorderStyle = BorderStyle.FixedSingle,
                BackColor = Color.White
            };
        }

        public MainForm()
        {
            Text = "Ik Core SGBPACK Builder";
            ClientSize = new Size(690, 500);
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            MinimizeBox = true;
            BackColor = Color.White;
            Font = new Font("Segoe UI", 9.0f, FontStyle.Regular);
            AutoScaleMode = AutoScaleMode.Dpi;

            Icon embeddedIcon = LoadEmbeddedIkCoreIcon();
            if (embeddedIcon != null)
                Icon = embeddedIcon;

            BuildMenu();
            BuildHeader();
            BuildFields();
            BuildOptions();
            BuildBottom();

            AcceptButton = FindBuildButton();
            SetReadyStatus("Listo para crear un SGBPACK1.");
        }

        private void BuildMenu()
        {
            MenuStrip menu = new MenuStrip();
            menu.BackColor = Color.White;
            menu.Font = new Font("Segoe UI", 9.0f);

            ToolStripMenuItem file = new ToolStripMenuItem("Archivo");
            ToolStripMenuItem create = new ToolStripMenuItem("Crear SGBPACK1");
            create.Click += delegate { BuildClicked(this, EventArgs.Empty); };
            ToolStripMenuItem exit = new ToolStripMenuItem("Salir");
            exit.Click += delegate { Close(); };
            file.DropDownItems.Add(create);
            file.DropDownItems.Add(new ToolStripSeparator());
            file.DropDownItems.Add(exit);

            ToolStripMenuItem tools = new ToolStripMenuItem("Herramientas");
            ToolStripMenuItem verify = new ToolStripMenuItem("Verificar archivos seleccionados");
            verify.Click += delegate { VerifySelectedFiles(); };
            ToolStripMenuItem clear = new ToolStripMenuItem("Limpiar formulario");
            clear.Click += delegate { ClearForm(); };
            tools.DropDownItems.Add(verify);
            tools.DropDownItems.Add(clear);

            ToolStripMenuItem help = new ToolStripMenuItem("Ayuda");
            ToolStripMenuItem about = new ToolStripMenuItem("Acerca de Ik Core SGBPACK Builder");
            about.Click += delegate {
                MessageBox.Show(this,
                    "Ik Core SGBPACK Builder v1.1\r\n\r\n" +
                    "Crea archivos SGBPACK1 para Ik Core.\r\n\r\n" +
                    "Proyecto no oficial e independiente.\r\n" +
                    "No incluye ROMs, BIOS ni boot ROMs.",
                    "Acerca de Ik Core SGBPACK Builder",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
            };
            help.DropDownItems.Add(about);

            menu.Items.Add(file);
            menu.Items.Add(tools);
            menu.Items.Add(help);
            MainMenuStrip = menu;
            Controls.Add(menu);
        }

        private void BuildHeader()
        {
            PictureBox logo = new PictureBox {
                Location = new Point(20, 47),
                Size = new Size(86, 86),
                SizeMode = PictureBoxSizeMode.Zoom,
                BackColor = Color.White
            };

            Bitmap logoBitmap = LoadApprovedIkCoreBitmap();
            if (logoBitmap != null)
                logo.Image = logoBitmap;
            Controls.Add(logo);

            Label title = new Label {
                Text = "Ik Core SGBPACK Builder",
                Font = new Font("Segoe UI", 17.5f, FontStyle.Bold),
                AutoSize = true,
                Location = new Point(121, 58),
                ForeColor = Color.FromArgb(22, 22, 22)
            };
            Controls.Add(title);

            Label sub = new Label {
                Text = "Crea archivos SGBPACK1 para Ik Core",
                Font = new Font("Segoe UI", 10.0f, FontStyle.Regular),
                AutoSize = true,
                Location = new Point(123, 96),
                ForeColor = Color.FromArgb(85, 85, 85)
            };
            Controls.Add(sub);
        }

        private void BuildFields()
        {
            AddFileRow("ROM de Game Boy:", 151, gbBox,
                "ROM Game Boy (*.gb;*.gbc)|*.gb;*.gbc|Todos los archivos (*.*)|*.*",
                delegate(string path) {
                    try
                    {
                        GbInfo info = SgbPack.InspectGameBoy(path, false);
                        titleBox.Text = info.Title;
                        idBox.Text = MakeId(info.Title);
                        SetReadyStatus("ROM de Game Boy cargada: " + info.Title);
                    }
                    catch (Exception ex)
                    {
                        SetErrorStatus(ex.Message);
                    }
                });

            AddFileRow("Programa SGB (BIOS):", 190, sgbBox,
                "Programa Super Game Boy (*.sfc;*.smc)|*.sfc;*.smc|Todos los archivos (*.*)|*.*",
                delegate(string path) {
                    SetReadyStatus("Programa SGB seleccionado.");
                });

            AddFileRow("Boot ROM (opcional):", 229, bootBox,
                "Boot ROM SGB (*.rom;*.bin)|*.rom;*.bin|Todos los archivos (*.*)|*.*",
                delegate(string path) {
                    SetReadyStatus("Boot ROM seleccionada.");
                });

            AddLabel("Título del juego:", 276);
            titleBox.Location = new Point(180, 272);
            titleBox.Size = new Size(478, 25);
            Controls.Add(titleBox);

            AddLabel("ID / Código:", 315);
            idBox.Location = new Point(180, 311);
            idBox.Size = new Size(478, 25);
            Controls.Add(idBox);

            AddLabel("Región:", 354);
            regionBox.Location = new Point(180, 350);
            regionBox.Size = new Size(170, 27);
            regionBox.DropDownStyle = ComboBoxStyle.DropDownList;
            regionBox.Font = new Font("Segoe UI", 9.5f);
            regionBox.Items.AddRange(new object[] { "Automática", "Japón", "Internacional" });
            regionBox.SelectedIndex = 0;
            Controls.Add(regionBox);
        }

        private void AddLabel(string text, int y)
        {
            Label lab = new Label {
                Text = text,
                Location = new Point(20, y),
                Size = new Size(150, 24),
                Font = new Font("Segoe UI", 9.4f)
            };
            Controls.Add(lab);
        }

        private void AddFileRow(string labelText, int y, TextBox box, string filter, Action<string> afterPick)
        {
            AddLabel(labelText, y + 4);

            box.Location = new Point(180, y);
            box.Size = new Size(370, 25);
            Controls.Add(box);

            Button button = new Button {
                Text = "Examinar...",
                Location = new Point(559, y - 1),
                Size = new Size(99, 28),
                Font = new Font("Segoe UI", 9.0f),
                BackColor = Color.FromArgb(248, 248, 248),
                FlatStyle = FlatStyle.System
            };
            button.Click += delegate {
                using (OpenFileDialog dlg = new OpenFileDialog()) {
                    dlg.Filter = filter;
                    dlg.CheckFileExists = true;
                    if (dlg.ShowDialog(this) == DialogResult.OK)
                    {
                        box.Text = dlg.FileName;
                        if (afterPick != null) afterPick(dlg.FileName);
                    }
                }
            };
            Controls.Add(button);
        }

        private void BuildOptions()
        {
            includeBoot.Text = "Incluir boot ROM";
            includeBoot.Location = new Point(20, 395);
            includeBoot.AutoSize = true;
            includeBoot.Checked = true;
            includeBoot.Font = new Font("Segoe UI", 9.2f);
            includeBoot.CheckedChanged += delegate {
                bootBox.Enabled = includeBoot.Checked;
            };
            Controls.Add(includeBoot);

            validateImage.Text = "Validar imagen";
            validateImage.Location = new Point(185, 395);
            validateImage.AutoSize = true;
            validateImage.Checked = true;
            validateImage.Font = new Font("Segoe UI", 9.2f);
            Controls.Add(validateImage);

            optimizeSize.Text = "Optimizar tamaño";
            optimizeSize.Location = new Point(335, 395);
            optimizeSize.AutoSize = true;
            optimizeSize.Checked = true;
            optimizeSize.Font = new Font("Segoe UI", 9.2f);
            Controls.Add(optimizeSize);

            ToolTip tip = new ToolTip();
            tip.SetToolTip(includeBoot,
                "SGBPACK1 v1 usado por Ik Core requiere una boot ROM SGB de 256 bytes.");
            tip.SetToolTip(validateImage,
                "Comprueba cabecera y checksum de la ROM Game Boy antes de crear el paquete.");
            tip.SetToolTip(optimizeSize,
                "Elimina únicamente una cabecera de copiador de 512 bytes si existe en el programa SGB.");
        }

        private RoundedButton FindBuildButton()
        {
            foreach (Control c in Controls)
                if (c is RoundedButton) return (RoundedButton)c;
            return null;
        }

        private void BuildBottom()
        {
            RoundedButton build = new RoundedButton {
                Text = "Crear SGBPACK1",
                Font = new Font("Segoe UI", 10.5f, FontStyle.Bold),
                Location = new Point(505, 384),
                Size = new Size(153, 38),
                CornerRadius = 7
            };
            build.Click += BuildClicked;
            Controls.Add(build);

            progressTrack.Location = new Point(20, 438);
            progressTrack.Size = new Size(638, 12);
            progressTrack.BackColor = Color.FromArgb(225, 225, 225);
            Controls.Add(progressTrack);

            progressFill.Location = new Point(0, 0);
            progressFill.Size = new Size(0, progressTrack.Height);
            progressFill.BackColor = Color.FromArgb(40, 190, 55);
            progressTrack.Controls.Add(progressFill);

            statusLabel.Location = new Point(20, 458);
            statusLabel.Size = new Size(638, 24);
            statusLabel.Font = new Font("Segoe UI", 9.0f);
            statusLabel.ForeColor = Color.FromArgb(45, 45, 45);
            Controls.Add(statusLabel);
        }

        private string MakeId(string title)
        {
            if (string.IsNullOrWhiteSpace(title)) return "";
            StringBuilder b = new StringBuilder();
            foreach (char ch in title.ToUpperInvariant())
            {
                if ((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9'))
                    b.Append(ch);
                if (b.Length >= 8) break;
            }
            return b.ToString();
        }

        private void SetProgress(int percent)
        {
            if (percent < 0) percent = 0;
            if (percent > 100) percent = 100;
            progressFill.Width = (progressTrack.ClientSize.Width * percent) / 100;
            progressFill.Height = progressTrack.ClientSize.Height;
            progressTrack.Refresh();
        }

        private void SetReadyStatus(string text)
        {
            statusLabel.ForeColor = Color.FromArgb(45, 45, 45);
            statusLabel.Text = text;
        }

        private void SetErrorStatus(string text)
        {
            statusLabel.ForeColor = Color.FromArgb(190, 35, 35);
            statusLabel.Text = "ERROR: " + text;
            SetProgress(0);
        }

        private void ClearForm()
        {
            gbBox.Clear();
            sgbBox.Clear();
            bootBox.Clear();
            titleBox.Clear();
            idBox.Clear();
            regionBox.SelectedIndex = 0;
            includeBoot.Checked = true;
            validateImage.Checked = true;
            optimizeSize.Checked = true;
            lastOutputPath = "";
            SetProgress(0);
            SetReadyStatus("Formulario limpio.");
        }

        private void VerifySelectedFiles()
        {
            try
            {
                if (string.IsNullOrWhiteSpace(gbBox.Text) ||
                    string.IsNullOrWhiteSpace(sgbBox.Text) ||
                    string.IsNullOrWhiteSpace(bootBox.Text))
                    throw new InvalidOperationException("Selecciona primero ROM GB, programa SGB y boot ROM.");

                SgbPack.InspectGameBoy(gbBox.Text, true);
                SgbPack.ValidateSgbProgram(sgbBox.Text);
                SgbPack.ValidateBoot(bootBox.Text);
                SetProgress(100);
                SetReadyStatus("Archivos verificados correctamente.");
                MessageBox.Show(this, "Los tres componentes son válidos para SGBPACK1 v1.",
                    "Ik Core SGBPACK Builder", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                SetErrorStatus(ex.Message);
                MessageBox.Show(this, ex.Message, "Ik Core SGBPACK Builder",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void BuildClicked(object sender, EventArgs e)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(gbBox.Text))
                    throw new InvalidOperationException("Selecciona la ROM de Game Boy.");
                if (string.IsNullOrWhiteSpace(sgbBox.Text))
                    throw new InvalidOperationException("Selecciona el programa SGB.");
                if (!includeBoot.Checked)
                    throw new InvalidOperationException(
                        "SGBPACK1 v1 requiere la boot ROM SGB. Activa \"Incluir boot ROM\".");
                if (string.IsNullOrWhiteSpace(bootBox.Text))
                    throw new InvalidOperationException("Selecciona la boot ROM SGB de 256 bytes.");

                SetProgress(15);
                SetReadyStatus("Validando componentes...");
                Refresh();

                GbInfo info = SgbPack.InspectGameBoy(gbBox.Text, validateImage.Checked);
                SgbPack.ValidateSgbProgram(sgbBox.Text);
                SgbPack.ValidateBoot(bootBox.Text);

                SetProgress(40);
                SetReadyStatus("Preparando SGBPACK1...");
                Refresh();

                string defaultTitle = string.IsNullOrWhiteSpace(titleBox.Text) ? info.Title : titleBox.Text;
                string safe = MakeSafeFileName(defaultTitle);
                if (string.IsNullOrWhiteSpace(safe)) safe = "Juego";

                using (SaveFileDialog dlg = new SaveFileDialog())
                {
                    dlg.Filter = "Ik Core SGBPACK1 (*.sfc)|*.sfc|Todos los archivos (*.*)|*.*";
                    dlg.FileName = safe + "_SGBPACK_v1.sfc";
                    dlg.AddExtension = true;
                    dlg.DefaultExt = "sfc";
                    if (!string.IsNullOrEmpty(lastOutputPath))
                    {
                        try { dlg.InitialDirectory = Path.GetDirectoryName(lastOutputPath); } catch { }
                    }
                    if (dlg.ShowDialog(this) != DialogResult.OK)
                    {
                        SetProgress(0);
                        SetReadyStatus("Creación cancelada.");
                        return;
                    }

                    lastOutputPath = dlg.FileName;
                    SetProgress(65);
                    SetReadyStatus("Escribiendo paquete...");
                    Refresh();

                    BuildResult r = SgbPack.Build(
                        sgbBox.Text,
                        gbBox.Text,
                        bootBox.Text,
                        dlg.FileName,
                        optimizeSize.Checked,
                        validateImage.Checked);

                    SetProgress(100);
                    statusLabel.ForeColor = Color.FromArgb(30, 100, 35);
                    statusLabel.Text = "SGBPACK1 creado correctamente.";

                    MessageBox.Show(this,
                        "SGBPACK1 creado y verificado correctamente.\r\n\r\n" +
                        "Título GB: " + r.Title + "\r\n" +
                        "Tamaño total: " + r.TotalBytes + " bytes\r\n" +
                        (string.IsNullOrEmpty(r.Note) ? "" : "\r\n" + r.Note),
                        "Ik Core SGBPACK Builder",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            }
            catch (Exception ex)
            {
                SetErrorStatus(ex.Message);
                MessageBox.Show(this, ex.Message, "Ik Core SGBPACK Builder",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private static string MakeSafeFileName(string text)
        {
            if (text == null) return "";
            foreach (char c in Path.GetInvalidFileNameChars())
                text = text.Replace(c, '_');
            return text.Trim();
        }
    }

    internal sealed class GbInfo
    {
        public string Title;
        public byte SgbFlag;
        public byte DestinationCode;
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

        public static GbInfo InspectGameBoy(string path, bool validateChecksum)
        {
            if (!File.Exists(path))
                throw new FileNotFoundException("No se encontró la ROM de Game Boy.");

            byte[] gb = File.ReadAllBytes(path);
            ValidateGameBoy(gb, validateChecksum);

            return new GbInfo {
                Title = GetTitle(gb),
                SgbFlag = gb[0x146],
                DestinationCode = gb[0x14A]
            };
        }

        public static void ValidateSgbProgram(string path)
        {
            if (!File.Exists(path))
                throw new FileNotFoundException("No se encontró el programa SGB.");

            long len = new FileInfo(path).Length;
            if (len < 32768)
                throw new InvalidDataException("El programa SGB seleccionado es demasiado pequeño.");
        }

        public static void ValidateBoot(string path)
        {
            if (!File.Exists(path))
                throw new FileNotFoundException("No se encontró la boot ROM SGB.");

            byte[] boot = File.ReadAllBytes(path);
            if (boot.Length != 256)
                throw new InvalidDataException("La boot ROM SGB debe medir exactamente 256 bytes.");
        }

        public static BuildResult Build(
            string sgbPath,
            string gbPath,
            string bootPath,
            string outPath,
            bool optimizeSize,
            bool validateChecksum)
        {
            if (!File.Exists(sgbPath)) throw new FileNotFoundException("No se encontró la ROM del programa SGB.");
            if (!File.Exists(gbPath)) throw new FileNotFoundException("No se encontró la ROM de Game Boy.");
            if (!File.Exists(bootPath)) throw new FileNotFoundException("No se encontró la boot ROM SGB.");

            byte[] sgb = File.ReadAllBytes(sgbPath);
            byte[] gb = File.ReadAllBytes(gbPath);
            byte[] boot = File.ReadAllBytes(bootPath);

            string note = null;

            if (optimizeSize && sgb.Length > 512 && (sgb.Length % 0x2000) == 512)
            {
                byte[] stripped = new byte[sgb.Length - 512];
                Buffer.BlockCopy(sgb, 512, stripped, 0, stripped.Length);
                sgb = stripped;
                note = "Se eliminó una cabecera de copiador de 512 bytes del programa SGB.";
            }

            if (sgb.Length < 32768)
                throw new InvalidDataException("La ROM SGB seleccionada es demasiado pequeña.");

            ValidateGameBoy(gb, validateChecksum);

            if (boot.Length != 256)
                throw new InvalidDataException("La boot ROM SGB debe medir exactamente 256 bytes.");

            bool bootMatches = true;
            for (int i = 0; i < BootSignature.Length; i++)
                if (boot[i] != BootSignature[i]) { bootMatches = false; break; }

            if (!bootMatches)
            {
                string warning = "Advertencia: la boot ROM mide 256 bytes, pero su firma inicial no coincide con la referencia SGB usada en el proyecto.";
                note = string.IsNullOrEmpty(note) ? warning : note + "\r\n" + warning;
            }

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

            using (FileStream fs = new FileStream(outPath, FileMode.Create, FileAccess.Write, FileShare.None))
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

        private static void ValidateGameBoy(byte[] gb, bool validateChecksum)
        {
            if (gb.Length < 0x150)
                throw new InvalidDataException("La ROM de Game Boy es demasiado pequeña.");

            for (int i = 0; i < NintendoLogo.Length; i++)
                if (gb[0x104 + i] != NintendoLogo[i])
                    throw new InvalidDataException("La cabecera no parece ser una ROM Game Boy válida.");

            if (validateChecksum)
            {
                int x = 0;
                for (int i = 0x134; i <= 0x14C; i++)
                    x = (x - gb[i] - 1) & 0xFF;
                if ((byte)x != gb[0x14D])
                    throw new InvalidDataException("La ROM Game Boy tiene checksum de cabecera inválido.");
            }
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
