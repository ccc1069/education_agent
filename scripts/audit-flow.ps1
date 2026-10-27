param([switch]$Extended, [switch]$Diagnostics, [switch]$AgentChecks)
# Live diagnostic script. Uses demo accounts and creates test data / learning records.
# Run only against the local demo instance. Extended and AgentChecks mutate demo state.
$ErrorActionPreference = 'Stop'
$base = 'http://localhost:8000'
$tokens = @{}
function Call-Api($method, $path, $role='', $data=$null) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $args = @{Uri=($base+$path); Method=$method; UseBasicParsing=$true; TimeoutSec=100}
    if ($role) { $args.Headers = @{Authorization=('Bearer '+$tokens[$role])} }
    if ($null -ne $data) {
        $args.ContentType='application/json; charset=utf-8'
        $args.Body=[Text.Encoding]::UTF8.GetBytes(($data | ConvertTo-Json -Depth 12 -Compress))
    }
    try {
        $resp=Invoke-WebRequest @args
        $reader=New-Object IO.StreamReader($resp.RawContentStream,[Text.Encoding]::UTF8)
        $raw=$reader.ReadToEnd()
        $obj=if($raw){$raw | ConvertFrom-Json}else{$null}
        return @{status=[int]$resp.StatusCode; seconds=[math]::Round($watch.Elapsed.TotalSeconds,2); data=$obj}
    } catch {
        $status=0
        $detail=if($_.ErrorDetails.Message){$_.ErrorDetails.Message}else{$_.Exception.Message}
        if($_.Exception.Response){
            $status=[int]$_.Exception.Response.StatusCode
            $reader=New-Object IO.StreamReader($_.Exception.Response.GetResponseStream(),[Text.Encoding]::UTF8)
            $responseText=$reader.ReadToEnd()
            if($responseText){$detail=$responseText}
        }
        return @{status=$status; seconds=[math]::Round($watch.Elapsed.TotalSeconds,2); error=$detail}
    }
}
function Show-Result($name,$result){
    Write-Output ($name+': '+($result | ConvertTo-Json -Depth 15 -Compress))
}
$roles=if($AgentChecks){@('student')}else{@('student','teacher','admin')}
foreach($role in $roles){
    $r=Call-Api POST '/api/v1/auth/login' '' @{email=($role+'@demo.com');password='demo123456'}
    if($r.status -ne 200){Show-Result ('login '+$role) $r;continue}
    $tokens[$role]=$r.data.access_token
    Show-Result ('login '+$role) @{status=$r.status;seconds=$r.seconds;user=$r.data.user}
}
if(!$tokens.student){exit 1}
if($AgentChecks){
    $ws=New-Object Net.WebSockets.ClientWebSocket
    try{
        $c=New-Object Threading.CancellationTokenSource
        $c.CancelAfter(15000)
        $ws.ConnectAsync([Uri]('ws://localhost:3000/ws/lrn_demo_student?token='+$tokens.student),$c.Token).GetAwaiter().GetResult() | Out-Null
        $c.Dispose()
        foreach($round in 1..3){
            $since=[DateTimeOffset]::UtcNow
            $c=New-Object Threading.CancellationTokenSource
            $c.CancelAfter(25000)
            $bytes=[Text.Encoding]::UTF8.GetBytes('{"action":"submit","knowledge_id":"logic","is_correct":false,"time_spent_seconds":45}')
            $ws.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,$c.Token).GetAwaiter().GetResult() | Out-Null
            foreach($i in 1..10){
                $buffer=New-Object byte[] 65536
                $recv=$ws.ReceiveAsync([ArraySegment[byte]]::new($buffer),$c.Token).GetAwaiter().GetResult()
                if($recv.MessageType -ne [Net.WebSockets.WebSocketMessageType]::Text){break}
                $frame=[Text.Encoding]::UTF8.GetString($buffer,0,$recv.Count) | ConvertFrom-Json
                if($frame.timestamp -and ([DateTimeOffset]::Parse($frame.timestamp)) -ge $since){
                    Show-Result ('wrong answer round '+$round) $frame
                    if($frame.event_type -eq 'tutor.teaching_response'){break}
                }
            }
            $c.Dispose()
        }
    }catch{Show-Result 'agent checks error' @{message=$_.Exception.Message}}
    finally{$ws.Abort();$ws.Dispose()}
    exit
}
if($Diagnostics){
    foreach($i in 1..6){
        $p=Call-Api GET '/api/v1/progress/lrn_demo_student' student
        Show-Result ('progress consistency '+$i) @{status=$p.status;mastery=$p.data.progress.quadratic_eq;attempts=$p.data.overall.total_attempts}
    }
    foreach($path in @('/api/v1/privacy/consent','/api/v1/notifications/preferences','/api/v1/admin/tasks/history','/api/v1/audit/verify')){
        $role=if($path -match '/admin/|/audit/'){'admin'}else{'student'}
        Show-Result $path (Call-Api GET $path $role)
    }
    $ws=New-Object Net.WebSockets.ClientWebSocket
    $cancel=New-Object Threading.CancellationTokenSource
    $cancel.CancelAfter(20000)
    try{
        $uri=[Uri]('ws://localhost:3000/ws/lrn_demo_student?token='+$tokens.student)
        $ws.ConnectAsync($uri,$cancel.Token).GetAwaiter().GetResult()
        Show-Result 'websocket nginx connect' @{state=$ws.State.ToString()}
        $bytes=[Text.Encoding]::UTF8.GetBytes('{"action":"question","knowledge_id":"arithmetic","question":"Explain how to check multiplication using division."}')
        $ws.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,$cancel.Token).GetAwaiter().GetResult()
        foreach($i in 1..10){
            $buffer=New-Object byte[] 65536
            $recv=$ws.ReceiveAsync([ArraySegment[byte]]::new($buffer),$cancel.Token).GetAwaiter().GetResult()
            if($recv.MessageType -ne [Net.WebSockets.WebSocketMessageType]::Text){break}
            $frame=[Text.Encoding]::UTF8.GetString($buffer,0,$recv.Count) | ConvertFrom-Json
            Show-Result ('websocket frame '+$i) $frame
            if($frame.event_type -eq 'tutor.teaching_response'){break}
        }
    }catch{Show-Result 'websocket error' @{message=$_.Exception.Message}}
    finally{$ws.Abort();$ws.Dispose();$cancel.Dispose()}
    exit
}
if($Extended){
    $newQuestion=Call-Api POST '/api/v1/questions/generate' teacher @{knowledge_id='quadratic_eq';question_type='multiple_choice';difficulty=2;use_rag=$false}
    Show-Result 'generate extended test question' $newQuestion
    if($newQuestion.status -ne 201){exit 1}
    $testQuestionId=$newQuestion.data.id
    Show-Result 'student draft list exposure' (Call-Api GET '/api/v1/questions?status=draft&limit=4' student)
    Show-Result 'student draft detail' (Call-Api GET ('/api/v1/questions/'+$testQuestionId) student)
    Show-Result 'personalized question on mastered arithmetic' (Call-Api POST '/api/v1/question' student @{knowledge_id='arithmetic';question='How do I check 12 divided by 3? Please use my current learning level.'})
    Show-Result 'generated question review' (Call-Api POST ('/api/v1/questions/'+$testQuestionId+'/status') teacher @{new_status='review'})
    Show-Result 'generated question publish' (Call-Api POST ('/api/v1/questions/'+$testQuestionId+'/status') teacher @{new_status='published'})
    Show-Result 'student generated question detail' (Call-Api GET ('/api/v1/questions/'+$testQuestionId) student)
    $class=Call-Api POST '/api/v1/teacher/classes' teacher @{name='AUDIT-20261013';description='Synthetic end-to-end test class'}
    Show-Result 'create audit class' $class
    if($class.status -eq 201){
        Show-Result 'join audit class' (Call-Api POST '/api/v1/teacher/classes/join' student @{invite_code=$class.data.invite_code})
        $assignment=Call-Api POST '/api/v1/teacher/assignments' teacher @{title='AUDIT-20261013';class_id=$class.data.id;question_ids=@($testQuestionId);description='Synthetic end-to-end test assignment'}
        Show-Result 'create audit assignment' $assignment
        if($assignment.status -eq 201){
            Show-Result 'publish audit assignment' (Call-Api POST ('/api/v1/teacher/assignments/'+$assignment.data.id+'/status') teacher @{new_status='published'})
            Show-Result 'student audit assignment' (Call-Api GET ('/api/v1/teacher/assignments/'+$assignment.data.id) student)
            Show-Result 'student answer check' (Call-Api POST ('/api/v1/questions/'+$testQuestionId+'/check') student @{student_answer=$newQuestion.data.answer})
            Show-Result 'teacher audit dashboard' (Call-Api GET ('/api/v1/teacher/classes/'+$class.data.id+'/dashboard') teacher)
        }
    }
    Show-Result 'debate' (Call-Api POST '/api/v1/question' student @{knowledge_id='arithmetic';question='Why is 2+3=5? Guide a beginner.';debate_mode=$true})
    Add-Type -AssemblyName System.Drawing
    $bmp=New-Object Drawing.Bitmap(600,200)
    $g=[Drawing.Graphics]::FromImage($bmp)
    $g.Clear([Drawing.Color]::White)
    $font=New-Object Drawing.Font('Arial',26)
    $g.DrawString('Solve: x^2 - 5x + 6 = 0',$font,[Drawing.Brushes]::Black,20,65)
    $stream=New-Object IO.MemoryStream
    $bmp.Save($stream,[Drawing.Imaging.ImageFormat]::Png)
    $image='data:image/png;base64,'+[Convert]::ToBase64String($stream.ToArray())
    Show-Result 'vision synthetic math' (Call-Api POST '/api/v1/vision/analyze' student @{images=@($image);knowledge_id='quadratic_eq';learner_message='Help me solve this problem.'})
    $g.Dispose();$bmp.Dispose();$font.Dispose();$stream.Dispose()
    exit
}
$me=Call-Api GET '/api/v1/auth/me' student
Show-Result 'student profile' $me
$learner=$me.data.learner_id
foreach($path in @('/api/v1/knowledge-graph',('/api/v1/progress/'+$learner),'/api/v1/questions?limit=3','/api/v1/teacher/assignments/mine','/api/v1/notifications/unread-count')){
    Show-Result $path (Call-Api GET $path student)
}
foreach($path in @('/api/v1/teacher/classes','/api/v1/teacher/assignments','/api/v1/knowledge-base/documents')){
    Show-Result $path (Call-Api GET $path teacher)
}
foreach($path in @('/api/v1/tenants','/api/v1/admin/tasks','/api/v1/admin/tasks/queue/stats','/api/v1/audit/verify')){
    Show-Result $path (Call-Api GET $path admin)
}
Show-Result 'student forbidden admin' (Call-Api GET '/api/v1/tenants' student)
Show-Result 'RAG search' (Call-Api POST '/api/v1/knowledge-base/search' teacher @{query='quadratic equation';top_k=3;min_score=0.0})
Show-Result 'RAG upload' (Call-Api POST '/api/v1/knowledge-base/documents' teacher @{title='AUDIT-20261013';content='Audit test: A quadratic equation has form ax^2+bx+c=0 with a nonzero. The discriminant is b^2-4ac.';metadata=@{audit=$true}})
Show-Result 'student question' (Call-Api POST '/api/v1/question' student @{knowledge_id='quadratic_eq';question='For x^2-5x+6=0, guide me through factoring and checking the roots.'})
Show-Result 'student submit' (Call-Api POST '/api/v1/submit' student @{knowledge_id='quadratic_eq';is_correct=$true;time_spent_seconds=30})
Show-Result 'student message' (Call-Api POST '/api/v1/message' student @{knowledge_id='quadratic_eq';message='Why do both roots satisfy the equation?'})
Show-Result 'question generation' (Call-Api POST '/api/v1/questions/generate' teacher @{knowledge_id='quadratic_eq';question_type='multiple_choice';difficulty=2;use_rag=$false})
Show-Result 'question generation RAG' (Call-Api POST '/api/v1/questions/generate' teacher @{knowledge_id='quadratic_eq';question_type='multiple_choice';difficulty=2;use_rag=$true})
Show-Result 'student progress after' (Call-Api GET ('/api/v1/progress/'+$learner) student)
