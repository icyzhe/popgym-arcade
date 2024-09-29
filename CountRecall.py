from typing import Optional, Tuple

import chex
import jax
import jax.numpy as jnp
from flax import struct
from gymnax.environments import environment, spaces
from functools import partial

@struct.dataclass
class EnvState:    
    timestep: int
    value_cards: jnp.ndarray
    query_cards: jnp.ndarray
    running_count: jnp.ndarray
    history: jnp.ndarray
    default_action: int


@struct.dataclass
class EnvParams:
    pass

@jax.jit
def process_action(state: EnvState, action: int) -> EnvState:
    new_default_action = jnp.where(action == 1, state.default_action + 1, state.default_action - 1)
    return state.replace(default_action=new_default_action)


class CountRecall(environment.Environment):
    def __init__(self, num_decks=1, num_types=2, fully_observable=False):
        super().__init__()
        self.fully_observable = fully_observable
        self.decksize = 52
        # self.error_clamp = error_clamp # NOT IMPLEMENTED
        self.num_decks = num_decks 
        self.num_types = num_types
        self.num_cards = self.decksize * self.num_decks 
        self.max_num = self.num_cards // self.num_types #每种牌的数量
        self.reward_scale = 1.0 / self.num_cards
        # self.default_action = 0
    
    @property
    def default_params(self) -> EnvParams:
        return EnvParams()

    def step_env(
        self, key: chex.PRNGKey, state: EnvState, action: int, params: EnvParams
    ) -> Tuple[chex.Array, EnvState, float, bool, dict]:

        running_count = state.running_count.at[state.value_cards[state.timestep]].add(1)
        prev_count = state.running_count[state.query_cards[state.timestep]]

        # state.default_action = process_action(state.default_action, action)

        new_state = process_action(state, action)


        reward = jnp.where(new_state.default_action == prev_count, self.reward_scale, -self.reward_scale)

        history = state.history.at[state.timestep].set(state.value_cards[state.timestep])

        # new_state = EnvState(
        #     state.timestep + 1, state.value_cards, state.query_cards, running_count, history, state.default_action
        # )
        new_state = new_state.replace(
            timestep=state.timestep + 1, 
            running_count=running_count, 
            history=history
        )
        # new_state = new_state.replace(history=update_history)
        obs = self.get_obs(new_state)
        terminated = new_state.timestep == self.num_cards

        return obs, new_state, reward, terminated, {}

    def reset_env(self, key: chex.PRNGKey, params: EnvParams) -> Tuple[chex.Array, EnvState]:
        """Performs resetting of environment."""
        key, key_value, key_query = jax.random.split(key, 3)
        cards = jnp.arange(self.decksize * self.num_decks) % self.num_types
        value_cards = jax.random.permutation(key_value, cards) # 2 1 3 2 0 3
        query_cards = jax.random.permutation(key_query, cards) # 3 0 2 1 3 2
        running_count = jnp.zeros((self.num_types,))
        history = jnp.zeros(self.num_cards)
        state = EnvState(
            timestep=0,
            value_cards=value_cards,
            query_cards=query_cards,
            running_count=running_count,
            history=history,
            default_action=0,
        )
        # obs = state.cards[state.timestep]
        obs = self.get_obs(state)
        return obs, state

    def get_obs(self, state: EnvState) -> chex.Array:
        """Returns observation from the state."""
        if self.fully_observable:
            # FOMDP
            current_card = jnp.zeros(self.num_types)
            current_card = current_card.at[state.value_cards[state.timestep]].set(1)

            query_card = jnp.zeros(self.num_types)
            query_card = query_card.at[state.query_cards[state.timestep]].set(1)

            # history = jnp.sum(state.history[:state.timestep], axis=0)

            return jnp.concatenate([current_card, query_card, state.history])
        
        elif self.fully_observable == False:
            # POMDP
            obs = jnp.zeros((2 * self.num_types))
            obs = obs.at[state.value_cards[state.timestep]].set(1)
            obs = obs.at[self.num_types + state.query_cards[state.timestep]].set(1)
        return obs

    def action_space(self, params: Optional[EnvParams] = None) -> spaces.Discrete:
        """Action space of the environment."""
        return spaces.Discrete(2)

    def observation_space(self, params: EnvParams) -> spaces.Box:
        """Observation space of the environment."""
        # according to self.fully_observable == False or True, return spaces.Box
        def true_fomdp():
            return spaces.BoX(
                jnp.zeros((3 * self.num_types,)),
                jnp.ones((3 * self.num_types,)),
                (2 * self.num_types + self.num_cards,),
                dtype=jnp.float32,
            )
        def false_pomdp():
            return spaces.Box(
                jnp.zeros((2 * self.num_types,)),
                jnp.ones((2 * self.num_types,)),
                (2 * self.num_types,),
                dtype=jnp.float32,
            )
        result = jax.lax.cond(self.fully_observable, true_fomdp, false_pomdp)
        return result


class CountRecallEasy(CountRecall):
    def __init__(self):
        super().__init__(num_decks=1, num_types=2)


class CountRecallMedium(CountRecall):
    def __init__(self):
        super().__init__(num_decks=2, num_types=4)


class CountRecallHard(CountRecall):
    def __init__(self):
        super().__init__(num_decks=4, num_types=13)

class FullyObservableCountRecallEasy(CountRecall):
    def __init__(self):
        super().__init__(num_decks=1, num_types=2, fully_observable=True)
        # 52 * 1 = 52 cards, 2 types of cards

class FullyObservableCountRecallMedium(CountRecall):
    def __init__(self):
        super().__init__(num_decks=2, num_types=4, fully_observable=True)
        # 52 * 2 = 104 cards, 4 types of cards

class FullyObservableCountRecallHard(CountRecall):
    def __init__(self):
        super().__init__(num_decks=4, num_types=13, fully_observable=True)
        # 52 * 4 = 208 cards, 13 types of cards