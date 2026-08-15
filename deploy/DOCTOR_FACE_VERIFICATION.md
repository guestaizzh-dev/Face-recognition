# 医生刷脸接入约定

本仓库只提供人脸核验判定服务，医生账号、登录态和排班属于 `chbzg` 业务系统。业务系统必须在以下三个业务事件调用一次核验：

| 业务事件 | `scene` | `action` | 触发规则 |
| --- | --- | --- | --- |
| 医生登录 | `login` | `login` | 密码校验通过、建立登录态之前 |
| 上午随机核验 | `attendance` | `morning` | 每位在岗医生每天 09:00-12:00 随机一次 |
| 下午随机核验 | `attendance` | `afternoon` | 每位在岗医生每天 14:00-17:00 随机一次 |

## 一次核验的调用顺序

1. `chbzg` 后端用服务端密钥调用 `POST /v1/internal/verification-sessions`，提交 `subject_type=doctor`、医生 ID、唯一 `business_event_id`、上述 `scene/action` 和登录管理员 ID（如有）。不要把密钥放到浏览器。
2. 后端把返回的 `session_id`、短期 `upload_token`、动作列表和过期时间交给当前页面。页面按动作采集摄像头帧，调用 `POST /v1/verification-sessions/{session_id}/verify`，使用 `Authorization: Bearer <upload_token>`。
3. 只有 `passed=true` 且有 `proof_id` 时才允许登录或确认考勤。业务后端随后调用 `POST /v1/internal/proofs/introspect` 校验 proof，并在业务事务成功后调用 `POST /v1/internal/proofs/{proof_id}/finalize`，传入同一个 `business_event_id`。
4. 任意失败、超时、重复消费或 proof 校验失败都必须拒绝本次业务操作；不能降级为仅密码登录或仅打卡成功。

## 幂等和随机时间

- `business_event_id` 必须由业务系统生成并持久化，例如 `doctor:{doctor_id}:attendance:{yyyy-mm-dd}:morning`。重试同一事件必须复用同一个 ID，不得创建第二次业务记录。
- 上午和下午随机时间由 `chbzg` 的服务端调度器生成并持久化，不能由浏览器随机，也不能由本服务定时触发，因为本服务无法打开医生页面或建立登录态。
- 调度器应在随机时间创建一个待核验任务，医生下一次访问业务页面时弹出刷脸流程；窗口结束仍未完成时标记缺失并进入业务侧补核验流程。

## 上线检查

- 正式域名 Origin 只允许 `https://cd.chbzg.com.cn`，测试域名 Origin 只允许 `https://shualian.chbzg.com.cn`。
- 两个环境使用不同的 API key、模板加密密钥和 SQLite 数据库，禁止共用人脸模板库。
- 反向代理分别把 HTTPS 请求转发到本机 `127.0.0.1:9003` 和 `127.0.0.1:9004`，并保留 `X-Forwarded-For`。
- 部署后检查 `/api/health`、`/api/ready`，再用测试医生完成登录、上午和下午三种事件的完整 proof 消费链路。
