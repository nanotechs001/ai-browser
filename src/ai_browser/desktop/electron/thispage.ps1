# "This page" for AI Browser's floating chat, on Windows: the address and title of the Brave window highest on the
# screen, read with UI Automation. AI Browser's own app runs this file as it is (thispage.js), with no argument: it is
# never built from a page's or the user's text. It only reads. When Brave isn't running, it says so and Brave stays
# closed. It prints one line of JSON: {"state": "ok", "url", "title"}, {"state": "closed"} or {"state": "nowindow"};
# anything that breaks prints {"state": "failed"}.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Say($answer) {
  [Console]::Out.Write((ConvertTo-Json -InputObject $answer -Compress))
}

try {
  $running = @(Get-Process -Name 'brave' -ErrorAction SilentlyContinue)
  if ($running.Count -eq 0) { Say @{ state = 'closed' }; exit 0 }
  # Brave's own process holds its windows: its main window is the Brave window highest on the screen.
  $front = @($running | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero } | Select-Object -First 1)
  if ($front.Count -eq 0) { Say @{ state = 'nowindow' }; exit 0 }
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  $window = [System.Windows.Automation.AutomationElement]::FromHandle($front[0].MainWindowHandle)
  $name = [string]$window.Current.Name
  $cut = $name.LastIndexOf(' - Brave')
  $title = if ($cut -ge 0) { $name.Substring(0, $cut) } else { $name }
  $isEdit = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit)
  # The address bar: the window's first edit box (the toolbar comes before the page)
  $bar = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $isEdit)
  $url = ''
  if ($null -ne $bar) {
    $value = $null
    if ($bar.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$value)) {
      $url = [string]$value.Current.Value
    }
  }
  Say @{ state = 'ok'; url = $url; title = $title }
} catch {
  Say @{ state = 'failed' }
}
