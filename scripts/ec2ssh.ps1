param([string]$Cmd)
$key = "C:\DEV\MindAI\mindai-key.pem"
$ec2 = "ubuntu@3.18.184.84"
C:\Windows\System32\OpenSSH\ssh.exe -i $key -o StrictHostKeyChecking=no $ec2 $Cmd
