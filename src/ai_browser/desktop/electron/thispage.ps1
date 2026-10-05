# "This page" for AI Browser's floating chat, on Windows: the address and title of the Brave window highest on the
# screen, read with UI Automation. AI Browser's own app runs this file as it is (thispage.js), with no argument: it is
# never built from a page's or the user's text. It only reads. When Brave isn't running, it says so and Brave stays
# closed. It prints one line of JSON: {"state": "ok", "url", "title"}, {"state": "closed"}, {"state": "nowindow"} or
# {"state": "unknown"} (the window has no address bar of Brave's own: an installed web app, full screen); anything that
# breaks prints {"state": "failed"}. The address comes from Brave's own address bar only, never from the page.
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
  # The address bar: Chromium's own edit box (its class is OmniboxViewViews), searched in the window's frame only,
  # breadth first. A page (a Document) is never searched: its fields could carry any name, and are never read.
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $queue = New-Object System.Collections.Queue
  $queue.Enqueue($window)
  $bar = $null
  $looked = 0
  while ($null -eq $bar -and $queue.Count -gt 0 -and $looked -lt 3000) {
    $child = $walker.GetFirstChild($queue.Dequeue())
    while ($null -ne $child -and $null -eq $bar) {
      $looked++
      $kind = $child.Current.ControlType
      if ($kind -eq [System.Windows.Automation.ControlType]::Document) {
        # the page, with everything in it: skipped
      } elseif ($kind -eq [System.Windows.Automation.ControlType]::Edit -and
                $child.Current.ClassName -eq 'OmniboxViewViews') {
        $bar = $child
      } else {
        $queue.Enqueue($child)
      }
      $child = $walker.GetNextSibling($child)
    }
  }
  if ($null -eq $bar) { Say @{ state = 'unknown' }; exit 0 }  # no address bar of Brave's own: the user picks
  $url = ''
  $value = $null
  if ($bar.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$value)) {
    $url = [string]$value.Current.Value
  }
  Say @{ state = 'ok'; url = $url; title = $title }
} catch {
  Say @{ state = 'failed' }
}
