
## bug
### 用户增加时区
### 需要控制同一账号多处登录
### 不可以连续收听音频

## `streamlit`
### caching
`session_state`会话状态只针对单个用户，对于其他用户是不可见的；而缓存针对所有用户，是共享的；`cache_data`返回是副本；`cache_resource`返回对象本身。
#### session_state
#### cache_data
#### cache_resource

### 代码更新

除`Home`和`pages/`下的代码能立即更新外，其他处与app相关的代码修改后，需要重启动app。