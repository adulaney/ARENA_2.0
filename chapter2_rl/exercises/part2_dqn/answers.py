# %%
import os

os.environ["ACCELERATE_DISABLE_RICH"] = "1"
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from dataclasses import dataclass
from typing import Optional, Union, List
import numpy as np
import gym
import gym.spaces
import gym.envs.registration
import plotly.express as px
import plotly.graph_objects as go
from tqdm import tqdm, trange
import sys
import time
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Union, Tuple
import torch as t
from torch import nn, Tensor
from gym.spaces import Discrete, Box
from numpy.random import Generator
import pandas as pd
import wandb
import pandas as pd
from pathlib import Path
from jaxtyping import Float, Int, Bool
import pytorch_lightning as pl
from pytorch_lightning.loggers import WandbLogger, CSVLogger

Arr = np.ndarray

# Make sure exercises are in the path
chapter = r"chapter2_rl"
exercises_dir = Path(
    f"{os.getcwd().split(chapter)[0]}/{chapter}/exercises").resolve()
section_dir = exercises_dir / "part2_dqn"
if str(exercises_dir) not in sys.path: sys.path.append(str(exercises_dir))

from part1_intro_to_rl.utils import make_env
from part1_intro_to_rl.solutions import Environment, Toy, Norvig, find_optimal_policy
import part2_dqn.utils as utils
import part2_dqn.tests as tests
from plotly_utils import line, cliffwalk_imshow, plot_cartpole_obs_and_dones

device = t.device("cuda" if t.cuda.is_available() else "cpu")

# %%
ObsType = int
ActType = int


class DiscreteEnviroGym(gym.Env[ActType, ObsType]):
    action_space: gym.spaces.Discrete
    observation_space: gym.spaces.Discrete

    def __init__(self, env: Environment):
        super().__init__()
        self.env = env
        self.observation_space = gym.spaces.Discrete(env.num_states)
        self.action_space = gym.spaces.Discrete(env.num_actions)
        self.reset()

    def step(self, action: ActType) -> Tuple[ObsType, float, bool, dict]:
        '''
        Samples from the underlying dynamics of the environment
        '''
        (states, rewards, probs) = self.env.dynamics(self.pos, action)
        idx = self.np_random.choice(len(states), p=probs)
        (new_state, reward) = (states[idx], rewards[idx])
        self.pos = new_state
        done = self.pos in self.env.terminal
        return (new_state, reward, done, {"env": self.env})

    def reset(self,
              seed: Optional[int] = None,
              return_info=False,
              options=None) -> Union[ObsType, Tuple[ObsType, dict]]:
        super().reset(seed=seed)
        self.pos = self.env.start
        return (self.pos, {"env": self.env}) if return_info else self.pos

    def render(self, mode="human"):
        assert mode == "human", f"Mode {mode} not supported!"


# %%
gym.envs.registration.register(
    id="NorvigGrid-v0",
    entry_point=DiscreteEnviroGym,
    max_episode_steps=100,
    nondeterministic=True,
    kwargs={"env": Norvig(penalty=-0.04)},
)

gym.envs.registration.register(id="ToyGym-v0",
                               entry_point=DiscreteEnviroGym,
                               max_episode_steps=2,
                               nondeterministic=False,
                               kwargs={"env": Toy()})


# %%
@dataclass
class Experience:
    '''A class for storing one piece of experience during an episode run'''
    obs: ObsType
    act: ActType
    reward: float
    new_obs: ObsType
    new_act: Optional[ActType] = None


@dataclass
class AgentConfig:
    '''Hyperparameters for agents'''
    epsilon: float = 0.1
    lr: float = 0.05
    optimism: float = 0


defaultConfig = AgentConfig()


class Agent:
    '''Base class for agents interacting with an environment (you do not need to add any implementation here)'''
    rng: np.random.Generator

    def __init__(self,
                 env: DiscreteEnviroGym,
                 config: AgentConfig = defaultConfig,
                 gamma: float = 0.99,
                 seed: int = 0):
        self.env = env
        self.config = config
        self.gamma = gamma
        self.num_actions = env.action_space.n
        self.num_states = env.observation_space.n
        self.name = type(self).__name__
        self.reset(seed)

    def get_action(self, obs: ObsType) -> ActType:
        raise NotImplementedError()

    def observe(self, exp: Experience) -> None:
        '''
        Agent observes experience, and updates model as appropriate.
        Implementation depends on type of agent.
        '''
        pass

    def reset(self, seed: int) -> None:
        self.rng = np.random.default_rng(seed)

    def run_episode(self, seed: int) -> List[int]:
        '''
        Simulates one episode of interaction, agent learns as appropriate
        Inputs:
            seed: Seed for the random number generator
        Outputs:
            The rewards obtained during the episode
        '''
        rewards = []
        obs = self.env.reset(seed=seed)
        self.reset(seed=seed)
        done = False
        while not done:
            act = self.get_action(obs)
            (new_obs, reward, done, info) = self.env.step(act)
            exp = Experience(obs, act, reward, new_obs)
            self.observe(exp)
            rewards.append(reward)
            obs = new_obs
        return rewards

    def train(self, n_runs=500):
        '''
        Run a batch of episodes, and return the total reward obtained per episode
        Inputs:
            n_runs : The number of episodes to simulate
        Outputs:
            The discounted sum of rewards obtained for each episode
        '''
        all_rewards = []
        for seed in trange(n_runs):
            rewards = self.run_episode(seed)
            all_rewards.append(utils.sum_rewards(rewards, self.gamma))
        return all_rewards


class Random(Agent):

    def get_action(self, obs: ObsType) -> ActType:
        return self.rng.integers(0, self.num_actions)


# %% Define the Cheater
class Cheater(Agent):

    def __init__(self,
                 env: DiscreteEnviroGym,
                 config: AgentConfig = defaultConfig,
                 gamma=0.99,
                 seed=0):
        super().__init__(env, config, gamma, seed)
        self.pi_opt = find_optimal_policy(env.unwrapped.env, gamma)

    def get_action(self, obs):
        return self.pi_opt[obs]


env_toy = gym.make("ToyGym-v0")
agents_toy: List[Agent] = [Cheater(env_toy), Random(env_toy)]
returns_list = []
names_list = []
for agent in agents_toy:
    returns = agent.train(n_runs=1000)
    returns_list.append(utils.cummean(returns))
    names_list.append(agent.name)

line(returns_list,
     names=names_list,
     title=f"Avg. reward on {env_toy.spec.name}")


# %%
class EpsilonGreedy(Agent):
    '''
    A class for SARSA and Q-Learning to inherit from.
    '''

    def __init__(self,
                 env: DiscreteEnviroGym,
                 config: AgentConfig = defaultConfig,
                 gamma: float = 0.99,
                 seed: int = 0):
        super().__init__(env, config, gamma, seed)

    def reset(self, seed: int) -> None:
        super().reset(seed)
        self.Q = np.zeros((self.num_states, self.num_actions)) + self.config.optimism


    def get_action(self, obs: ObsType) -> ActType:
        '''
        Selects an action using epsilon-greedy with respect to Q-value estimates
        '''
        if self.rng.random() < self.config.epsilon:
            return self.rng.integers(0, self.num_actions)
        else:
            return np.argmax(self.Q[obs])


class QLearning(EpsilonGreedy):

    def observe(self, exp: Experience) -> None:
        future_reward = self.gamma * np.max(self.Q[exp.new_obs])
        td_error = exp.reward + future_reward - self.Q[exp.obs, exp.act]
        self.Q[exp.obs, exp.act] += self.config.lr * td_error



class SARSA(EpsilonGreedy):

    def observe(self, exp: Experience):
        new_action = self.get_action(exp.new_obs)
        future_reward = self.gamma * self.Q[exp.new_obs, new_action]
        td_error = exp.reward + future_reward - self.Q[exp.obs, exp.act]
        self.Q[exp.obs, exp.act] += self.config.lr * td_error


n_runs = 1000
gamma = 0.99
seed = 1
env_norvig = gym.make("NorvigGrid-v0")
config_norvig = AgentConfig()
args_norvig = (env_norvig, config_norvig, gamma, seed)
agents_norvig: List[Agent] = [
    Cheater(*args_norvig),
    QLearning(*args_norvig),
    SARSA(*args_norvig),
    Random(*args_norvig)
]
returns_norvig = {}
fig = go.Figure(
    layout=dict(title_text=f"Avg. reward on {env_norvig.spec.name}",
                template="simple_white",
                xaxis_range=[-30, n_runs + 30]))
for agent in agents_norvig:
    returns = agent.train(n_runs)
    fig.add_trace(go.Scatter(y=utils.cummean(returns), name=agent.name))
fig.show()
# %%

