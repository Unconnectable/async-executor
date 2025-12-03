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

`spwan`: 调用 `spwan_inner`

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

    runnable.schedule(); // 调用生成的闭包,入队
    task
}
```

- `spawn_inner`
  - 在 `active` (Slab) 注册，获取一个空闲的东西
  - `AsyncCallOnDrop` 封装，确保 async 代码块会被销毁
  - `async_task::Builder` 创建 `Runnable` 和 `Task`,分别给用户和任务队列
  - `.spawn_unchecked` 触发 schedule 函数生成闭包
  - `runnable.schedule()` 触发闭包，然后入队。
- **`schedule`**：生成闭包 `move |runnable| { state.queue.push(runnable); state.notify(); }`。

调度闭包 (`schedule`)

调用的 `Self::schedule` 如下:

```rust
fn schedule(state: Pin<&'a State>) -> impl Fn(Runnable) + Send + Sync + 'a {
    // TODO: If possible, push into the current local queue and notify the ticker.
    move |runnable| {
        // 具体的动作:把任务放进队列
        let result = state.queue.push(runnable);
        debug_assert!(result.is_ok()); // Since we use unbounded queue, push will never fail.
        // 通知执行器有新活了,别睡了
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

`spawn` 做的事情是调用底层的 `spawn_inner`,创建任务,也就是我们的代码块,同事创建了 `callback` 函数,通过最后的 `.schedule` 把任务放进队列里面.

### `state()` 转换 把 AtomicPtr<State> 变为 Pin<&State>

```rust
unsafe fn spawn_inner<T: 'a>(
        state: Pin<&'a State>,
        future: impl Future<Output = T> + 'a,
        active: &mut Slab<Waker>,
) -> Task<T> {}

fn schedule(state: Pin<&'a State>) -> impl Fn(Runnable) + Send + Sync + 'a {}

pub fn spawn<T: Send + 'a>(&self, future: impl Future<Output = T> + Send + 'a) -> Task<T> {
        let state: Pin<&State> = self.state();
    let mut active = state.active();
    ///
}
```

spawn_inner 和 schedul 的参数要求是 Pin<&'a State>类型的，但是我们成员 State 是 pub(crate) state: AtomicPtr<State> ，

需要转换类型才能调用 State 结构体的方法 `.acticve` 等

### tick and try_tick ，实际的定义在 State 结构体中

```rust
    pub(crate) fn try_tick(&self) -> bool {
        match self.queue.pop() {
            Err(_) => false,
            Ok(runnable) => {
                // Notify another ticker now to pick up where this ticker left off, just in case
                // running the task takes a long time.
                self.notify();

                // Run the task.
                runnable.run();
                true
            }
        }
    }

    pub(crate) async fn tick(&self) {
        let runnable = Ticker::new(self).runnable().await;
        runnable.run();
    }
```

try_tick 在拿到任务后会会 notify 别的线程，如果没有会跳过返回 false，如果有就执行，返回真

tick 启动后如果任务队列是空的，会卡在这里 ，返回一个 Peding，直到有任务，有别的把他 noftify。异步等待

### `spwan_many`

```rust
pub fn spawn_many<T: 'a, F: Future<Output = T> + 'a>(
        &self,
        futures: impl IntoIterator<Item = F>,
        handles: &mut impl Extend<Task<F::Output>>,
    ) {
        let state = self.inner().state();
        let mut active = state.active();

        // Convert all of the futures to tasks.
        let tasks = futures.into_iter().map(|future| {
            // SAFETY: This executor is not thread safe, so the future and its result
            //         cannot be sent to another thread.
            unsafe { Executor::spawn_inner(state, future, &mut active) }

            // As only one thread can spawn or poll tasks at a time, there is no need
            // to release lock contention here.
        });

        // Push them to the user's collection.
        handles.extend(tasks);
    }
```

`active: Mutex<Slab<Waker>>` ，获取 actice 的锁 ，这样可以朝着 Waker 队列写东西

unsafe 中调用 spawn_inner 创见任务

在 handles 中添加创见的任务

#### 方法

- `spwan`: 调用 `spwan_inner`
- `spawn_inner`
  - 在 `active` (Slab) 注册,获取一个空闲的东西
  - `AsyncCallOnDrop` 封装,确保 async 代码块会被销毁
  - `async_task::Builder` 创建 `Runnable` 和 `Task`,分别给用户和任务队列
  - `.spawn_unchecked` 触发 schedule 函数生成闭包
  - `runnable.schedule()` 触发闭包,然后入队.
- **`schedule`**:生成闭包 `move |runnable| { state.queue.push(runnable); state.notify(); }`.
- **`run`**:调用 `self.state().run(future).await`.

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

## 附录:问题列表

````markdown
1.active: &mut Slab<Waker>
是一堆的 waker 开关吗?也就是比如有 10 个 waker 开关

let entry = active.vacant_entry(); // 在花名册里找个空位
let index = entry.key(); // 拿到这个空位的号码牌 (ID)

这里是随机找一个吗 比如我的 10 个 waker 有 5 个空的,就随便找一个 如果没有空的了?会扩容吗?
entry.key 是获取这个空的的号码吗 比如 5 号 10 号

2.  let future = AsyncCallOnDrop::new(future, move || drop(state.active().try_remove(index)));
    这里就是把我的外部的代码告诉系统 出现 panic!或者别的错误就结束

也就是 fn async{ xxx} 或者 async {
do something
}
这样的吗?

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

1.  这是 executor 的 fn run

```rust
    pub async fn run<T>(&self, future: impl Future<Output = T>) -> T {
        self.state().run(future).await
    }
```
````

sd 2.这是 executor 的 schedule 刚才用的是 runnable 的 schedule 还是这个,这个是干嘛的

`````rust
fn schedule(state: Pin<&'a State>) -> impl Fn(Runnable) + Send + Sync + 'a {
        // TODO: If possible, push into the current local queue and notify the ticker.
        move |runnable| {
            let result = state.queue.push(runnable);
            debug_assert!(result.is_ok()); // Since we use unbounded queue, push will never fail.
            state.notify();
        }
    }
1.  这是 executor 的 fn run

```rust
    pub async fn run<T>(&self, future: impl Future<Output = T>) -> T {
        self.state().run(future).await
    }
```

2.这是 executor 的 schedule 刚才用的是 runnable 的 schedule 还是这个,这个是干嘛的

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
