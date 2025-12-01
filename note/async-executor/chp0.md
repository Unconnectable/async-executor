# 目录

## `Excturor` 结构体分析

### 1. 定义

```rust
pub struct Executor<'a> {
    /// The executor state.
    pub(crate) state: AtomicPtr<State>, //定义653行
    /// Makes the `'a` lifetime invariant.
    _marker: PhantomData<std::cell::UnsafeCell<&'a ()>>,
}
```

- `State` 定义如下:
  ```rust
  struct State {
      queue: ConcurrentQueue<Runnable>,
      local_queues: RwLock<Vec<Arc<ConcurrentQueue<Runnable>>>>,
      notified: AtomicBool,
      sleepers: Mutex<Sleepers>,
      active: Mutex<Slab<Waker>>,
  }
  ```

### 2. 任务生成 (`spawn` 方法)

```rust
pub fn spawn<T: Send + 'a>(&self, future: impl Future<Output = T> + Send + 'a) -> Task<T> {
    let state = self.state();
    let mut active = state.active();

    // SAFETY: `T` and the future are `Send`.
    unsafe { Self::spawn_inner(state, future, &mut active) }
}
```

#### 2.1 `spawn_inner`

```rust
unsafe fn spawn_inner<T: 'a>(
    state: Pin<&'a State>,
    future: impl Future<Output = T> + 'a,
    active: &mut Slab<Waker>,
) -> Task<T> {
    // Remove the task from the set of active tasks when the future finishes.
    let entry = active.vacant_entry();
    let index = entry.key();
    let future = AsyncCallOnDrop::new(future, move || drop(state.active().try_remove(index)));

    let (runnable, task) = Builder::new()
        .propagate_panic(true)
        .spawn_unchecked(|()| future, Self::schedule(state)); // Self::schedule 生成闭包
    entry.insert(runnable.waker());

    runnable.schedule(); // 调用生成的闭包，入队
    task
}
```

### 3. 调度闭包 (`schedule`)

调用的 `Self::schedule` 如下：

```rust
fn schedule(state: Pin<&'a State>) -> impl Fn(Runnable) + Send + Sync + 'a {
    // TODO: If possible, push into the current local queue and notify the ticker.
    move |runnable| {
        // 具体的动作：把任务放进队列
        let result = state.queue.push(runnable);
        debug_assert!(result.is_ok()); // Since we use unbounded queue, push will never fail.
        // 通知执行器有新活了，别睡了
        state.notify();
    }
}
```

生成的闭包会在以下的方法处理

```
+-----------------------+
| Header (头部信息)      |  <-- 存着函数指针表 (vtable)
+-----------------------+
| Scheduler (调度闭包)   |  <-- callback 生成的闭包 存放在这里
+-----------------------+
| Future (你的代码)      |
+-----------------------+
| Output (结果存放处)    |
+-----------------------+
```

### 5. 最终总结 (原封不动)

`spawn` 做的事情是调用底层的 `spawn_inner`，创建任务，也就是我们的代码块，同事创建了 `callback` 函数，通过最后的 `.schedule` 把任务放进队列里面。

### 总结

#### `Executor` 结构体

用来管理任务和执行任务

#### 方法

- `spwan`: 调用 `spwan_inner`
- `spawn_inner`
  - 在 `active` (Slab) 注册，获取一个空闲的东西
  - `AsyncCallOnDrop` 封装，确保 async 代码块会被销毁
  - `async_task::Builder` 创建 `Runnable` 和 `Task`,分别给用户和任务队列
  - `.spawn_unchecked` 触发 schedule 函数生成闭包
  - `runnable.schedule()` 触发闭包，然后入队。
- **`schedule`**：生成闭包 `move |runnable| { state.queue.push(runnable); state.notify(); }`。
- **`run`**：调用 `self.state().run(future).await`。

```rust

```

sd

```rust

```

sd

```rust

```

sd

```rust

```

sd

```rust

```

sd

```rust

```

sd

```rust

```

sd

```rust

```

```rust

```

## 附录：问题列表

```markdown
1.active: &mut Slab<Waker>
是一堆的 waker 开关吗？也就是比如有 10 个 waker 开关

let entry = active.vacant_entry(); // 在花名册里找个空位
let index = entry.key(); // 拿到这个空位的号码牌 (ID)

这里是随机找一个吗 比如我的 10 个 waker 有 5 个空的，就随便找一个 如果没有空的了？会扩容吗？
entry.key 是获取这个空的的号码吗 比如 5 号 10 号

2.  let future = AsyncCallOnDrop::new(future, move || drop(state.active().try_remove(index)));
    这里就是把我的外部的代码告诉系统 出现 panic！或者别的错误就结束

也就是 fn async{ xxx} 或者 async {
do something
}
这样的吗？

3.  let (runnable, task) = Builder::new()
    .propagate_panic(true)
    .spawn_unchecked(|()| future, Self::schedule(state));

这里的 runnable 是什么 task 是什么 我看不懂
后面的两个调用是什么

4.

pub fn schedule(self) {
let ptr = self.ptr.as_ptr();
let header = ptr as \*const Header<M>;
mem::forget(self);

        unsafe {
            ((*header).vtable.schedule)(ptr, ScheduleInfo::new(false));
        }
    }
```

````markdown
1.  这是 executor 的 fn run

```rust
    pub async fn run<T>(&self, future: impl Future<Output = T>) -> T {
        self.state().run(future).await
    }
```
````

sd 2.这是 executor 的 schedule 刚才用的是 runnable 的 schedule 还是这个，这个是干嘛的

```rust
fn schedule(state: Pin<&'a State>) -> impl Fn(Runnable) + Send + Sync + 'a {
        // TODO: If possible, push into the current local queue and notify the ticker.
        move |runnable| {
            let result = state.queue.push(runnable);
            debug_assert!(result.is_ok()); // Since we use unbounded queue, push will never fail.
            state.notify();
        }
    }
```

`````markdown
1.  这是 executor 的 fn run

```rust
    pub async fn run<T>(&self, future: impl Future<Output = T>) -> T {
        self.state().run(future).await
    }
```

2.这是 executor 的 schedule 刚才用的是 runnable 的 schedule 还是这个，这个是干嘛的

````rust
fn schedule(state: Pin<&'a State>) -> impl Fn(Runnable) + Send + Sync + 'a {
        // TODO: If possible, push into the current local queue and notify the ticker.
        move |runnable| {
            let result = state.queue.push(runnable);
            debug_assert!(result.is_ok()); // Since we use unbounded queue, push will never fail.
            state.notify();
        }
    }
    ```

````
`````

```

```
